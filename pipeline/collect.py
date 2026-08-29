"""
ブランド公式サイズ表の抽出。

なぜLLMを使うか:
  サイズ表はブランドごとに構造がバラバラで、相当数が**画像**で掲載されている。
  HTMLのテキスト抽出だけでは到達できないため、画像入力に対応したモデルを使う。
  ここは「読み取り」であって「判断」ではないので、安価なモデル（Gemini Flash 無料枠）で足りる。

なぜ抽出結果をそのまま保存しないか:
  この事業でいちばん危ないのは、「服の実寸」を「犬の適合レンジ」と取り違えて
  保存することである（normalize.py 参照）。取り違えると全推薦が壊れる。
  そこで抽出結果は必ず validate() を通す。measure_basis の根拠となる
  **公式ページの原文引用**が取れていない抽出は、破棄する。推測では保存しない。
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Optional

from .normalize import DOG_FIT_RANGE, GARMENT_ACTUAL

API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-2.5-flash"

MIN_INTERVAL_SEC = 4.0        # 無料枠のレート制限に合わせて控えめに（15 RPM 相当）
MAX_RETRIES = 3               # 第30項: リトライ上限
DEFAULT_DAILY_CAP = 1200      # 無料枠 1500 req/日 の内側に収める

DIMS = ("neck", "chest", "back", "weight")


class CollectError(RuntimeError):
    pass


class QuotaExceeded(CollectError):
    pass


# --- 抽出の指示 ------------------------------------------------------

PROMPT = """あなたは犬服のサイズ表を読み取る専門家です。
与えられたページ（テキストまたは画像）から、サイズ表を正確に抜き出してください。

厳守すること:
1. 数値はページに書かれているとおりに写す。丸めない、補間しない、推測で埋めない。
2. 記載のない項目は null にする。0 で埋めてはいけない。
3. measure_basis は、その表の数値が何を指すかをページが明記している場合のみ答える。
   - 犬の体のサイズを指す  -> "dog_fit_range"
   - 服そのものの寸法を指す -> "garment_actual"
   明記がなければ null。推測しないこと。
4. measure_basis を答えた場合は、根拠となるページ上の一文を basis_quote に
   原文のまま（要約せず）入れること。
5. 単位は cm と kg に統一する。

出力は指定されたJSONスキーマに従うこと。"""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "brand_name": {"type": "string"},
        "category": {"type": "string", "enum": ["wear", "harness", "carrier"]},
        "measure_basis": {"type": "string", "nullable": True,
                          "enum": [DOG_FIT_RANGE, GARMENT_ACTUAL]},
        "basis_quote": {"type": "string", "nullable": True},
        "stretch": {"type": "string", "nullable": True,
                    "enum": ["none", "low", "high"]},
        "sizes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "neck_min": {"type": "number", "nullable": True},
                    "neck_max": {"type": "number", "nullable": True},
                    "chest_min": {"type": "number", "nullable": True},
                    "chest_max": {"type": "number", "nullable": True},
                    "back_min": {"type": "number", "nullable": True},
                    "back_max": {"type": "number", "nullable": True},
                    "weight_min": {"type": "number", "nullable": True},
                    "weight_max": {"type": "number", "nullable": True},
                },
                "required": ["label"],
            },
        },
    },
    "required": ["brand_name", "sizes"],
}


# --- 検証 ------------------------------------------------------------

@dataclass(frozen=True)
class Rejection:
    reason: str
    detail: str = ""


@dataclass
class Extraction:
    brand_name: str
    category: str = "wear"
    measure_basis: Optional[str] = None
    basis_quote: Optional[str] = None
    stretch: Optional[str] = None
    sizes: list[dict] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Extraction":
        return cls(
            brand_name=(d.get("brand_name") or "").strip(),
            category=d.get("category") or "wear",
            measure_basis=d.get("measure_basis") or None,
            basis_quote=(d.get("basis_quote") or "").strip() or None,
            stretch=d.get("stretch") or None,
            sizes=list(d.get("sizes") or []),
        )


# 小型犬メディアとして扱う範囲。極端な値は読み取り誤りの可能性が高い
PLAUSIBLE = {
    "neck":   (5.0, 80.0),
    "chest":  (10.0, 140.0),
    "back":   (5.0, 110.0),
    "weight": (0.2, 90.0),
}

MIN_QUOTE_LEN = 8


def validate(ex: Extraction) -> list[Rejection]:
    """保存してよいかを判定する。1件でも返れば保存しない。"""
    out: list[Rejection] = []

    if not ex.brand_name:
        out.append(Rejection("brand_missing", "ブランド名が取れていない"))

    if not ex.sizes:
        out.append(Rejection("no_rows", "サイズ行が1件もない"))

    # ここがこのモジュールの中心。取り違えると全推薦が壊れる
    if ex.measure_basis not in (DOG_FIT_RANGE, GARMENT_ACTUAL):
        out.append(Rejection(
            "basis_unknown",
            "表が『犬の実測』か『服の実寸』かをページが明記していない。推測で保存しない"))
    elif not ex.basis_quote or len(ex.basis_quote) < MIN_QUOTE_LEN:
        out.append(Rejection(
            "basis_quote_missing",
            f"measure_basis={ex.measure_basis} の根拠となる原文引用がない"))

    labels = set()
    for row in ex.sizes:
        label = str(row.get("label") or "").strip()
        if not label:
            out.append(Rejection("label_missing", f"サイズ名のない行: {row}"))
            continue
        if label in labels:
            out.append(Rejection("label_duplicated", f"サイズ名の重複: {label}"))
        labels.add(label)

        if not any(row.get(f"{d}_min") is not None or row.get(f"{d}_max") is not None
                   for d in DIMS):
            out.append(Rejection("row_empty", f"数値が1つもない行: {label}"))

        for d in DIMS:
            lo, hi = row.get(f"{d}_min"), row.get(f"{d}_max")
            if lo is not None and hi is not None and lo > hi:
                out.append(Rejection("range_inverted", f"{label} の {d}: {lo} > {hi}"))
            for v in (lo, hi):
                if v is None:
                    continue
                lim_lo, lim_hi = PLAUSIBLE[d]
                if not (lim_lo <= v <= lim_hi):
                    out.append(Rejection(
                        "value_implausible", f"{label} の {d}={v} は想定外の値"))

    return out


# --- Gemini クライアント ---------------------------------------------

def _default_fetch(url: str, payload: bytes, timeout: float = 60.0) -> tuple[int, str]:
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status, res.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


class GeminiExtractor:
    def __init__(self,
                 api_key: Optional[str] = None,
                 model: str = DEFAULT_MODEL,
                 fetch: Callable[[str, bytes], tuple[int, str]] = _default_fetch,
                 daily_cap: int = DEFAULT_DAILY_CAP,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not self.api_key:
            raise CollectError(
                "GEMINI_API_KEY が設定されていません。GitHub Secrets に登録してください。")
        self.model = model
        self._fetch = fetch
        self._sleep = sleep
        self._clock = clock
        self.daily_cap = int(os.environ.get("COLLECT_DAILY_CAP", daily_cap))
        self.calls = 0
        self._last_call_at: Optional[float] = None

    def _throttle(self) -> None:
        if self._last_call_at is None:
            return
        wait = MIN_INTERVAL_SEC - (self._clock() - self._last_call_at)
        if wait > 0:
            self._sleep(wait)

    def _body(self, text: Optional[str], image: Optional[tuple[str, bytes]]) -> bytes:
        parts: list[dict] = [{"text": PROMPT}]
        if text:
            parts.append({"text": text})
        if image:
            mime, blob = image
            parts.append({"inline_data": {
                "mime_type": mime,
                "data": base64.b64encode(blob).decode("ascii")}})
        return json.dumps({
            "contents": [{"parts": parts}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": RESPONSE_SCHEMA,
                "temperature": 0,     # 読み取り作業なので揺らがせない
            },
        }).encode("utf-8")

    def extract(self, text: Optional[str] = None,
                image: Optional[tuple[str, bytes]] = None) -> Extraction:
        """ページのテキストか画像（またはその両方）からサイズ表を読み取る。"""
        if not text and not image:
            raise CollectError("テキストか画像のどちらかが必要です")
        if self.calls >= self.daily_cap:
            raise QuotaExceeded(f"収集の日次上限 {self.daily_cap} 件に達したため停止しました。")

        url = f"{API_BASE}/{self.model}:generateContent?key={self.api_key}"
        body = self._body(text, image)
        last = ""

        for attempt in range(MAX_RETRIES):
            self._throttle()
            status, raw = self._fetch(url, body)
            self._last_call_at = self._clock()
            self.calls += 1

            if status == 200:
                return Extraction.from_dict(self._parse(raw))

            if status == 429 or 500 <= status < 600:
                last = f"HTTP {status}: {raw[:200]}"
                if attempt < MAX_RETRIES - 1:
                    self._sleep(MIN_INTERVAL_SEC * (2 ** attempt))
                continue

            raise CollectError(f"HTTP {status}: {raw[:300]}")

        raise CollectError(f"リトライ上限に達しました。{last}")

    @staticmethod
    def _parse(raw: str) -> dict:
        try:
            data = json.loads(raw)
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)
        except (KeyError, IndexError, TypeError) as e:
            raise CollectError(f"想定外のレスポンス構造です: {e}") from e
        except json.JSONDecodeError as e:
            raise CollectError(f"JSONとして読めません: {e}") from e


# --- SQL への変換 ----------------------------------------------------

def to_sql(ex: Extraction, brand_slug: str, source_url: str,
           fetched_at: str, brand_id: int, chart_id: int,
           source_id: int) -> str:
    """検証を通った抽出結果を、そのままレビューできるSQLにする。
    自動で本番DBに書き込まず、人（またはClaude）が差分を見てから取り込む。"""
    problems = validate(ex)
    if problems:
        raise CollectError("検証を通っていない抽出はSQLにしない: "
                           + "; ".join(p.reason for p in problems))

    def num(v):
        return "NULL" if v is None else str(v)

    quote = (ex.basis_quote or "").replace("'", "''")
    name = ex.brand_name.replace("'", "''")

    lines = [
        f"-- {name} / {ex.category} / {ex.measure_basis}",
        f"INSERT INTO source (id, kind, url, title, fetched_at, note) VALUES",
        f"  ({source_id},'brand_official','{source_url}','{name} サイズ表',"
        f"'{fetched_at}','原文: 「{quote}」→ {ex.measure_basis}');",
        f"INSERT INTO brand (id, slug, name) VALUES ({brand_id},'{brand_slug}','{name}');",
        f"INSERT INTO size_chart (id, brand_id, category, source_id, measure_basis, stretch)",
        f"  VALUES ({chart_id},{brand_id},'{ex.category}',{source_id},"
        f"'{ex.measure_basis}',{'NULL' if not ex.stretch else chr(39)+ex.stretch+chr(39)});",
        "INSERT INTO size_variant (chart_id,label,sort_order,"
        "neck_min,neck_max,chest_min,chest_max,back_min,back_max,"
        "weight_min,weight_max,provenance,source_id) VALUES",
    ]
    rows = []
    for i, r in enumerate(ex.sizes, start=1):
        label = str(r["label"]).replace("'", "''")
        rows.append(
            f"  ({chart_id},'{label}',{i},"
            + ",".join(num(r.get(f"{d}_{b}")) for d in DIMS for b in ("min", "max"))
            + f",'official',{source_id})")
    lines.append(",\n".join(rows) + ";")
    return "\n".join(lines)


def main() -> int:
    """日次パイプラインから呼ばれる入口。
    まだ収集対象のキューを繋いでいないので、鍵の有無だけを報告して終わる。
    ここで落ちると毎朝の失敗通知になるため、未接続は正常終了として扱う。"""
    if not os.environ.get("GEMINI_API_KEY"):
        print("collect: GEMINI_API_KEY が未設定のため、収集をスキップしました。")
        return 0
    print("collect: 収集キューは未接続です。対象URLの投入後に有効になります。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
