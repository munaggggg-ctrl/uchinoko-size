"""
楽天市場APIのクライアント（購入リンクと価格の取得）。

役割の切り分け:
  サイズデータの一次情報は「ブランド公式サイズ表」であり、このAPIではない。
  ここで取るのは購入導線（アフィリエイトURL・価格・在庫）だけ。
  モール側のAPIが止まってもサイズDBは無傷で残る、という設計を保つ。

規約と申告値の遵守:
  アプリ登録時に Expected QPS = 1 と申告しているので、クライアント側で
  秒間1リクエストに制限する。申告より速く叩かない。

認証情報:
  RAKUTEN_APP_ID / RAKUTEN_ACCESS_KEY / RAKUTEN_AFFILIATE_ID を環境変数から読む。
  コードにもリポジトリにも書かない（引継書 第34項）。

Referer が必須:
  楽天APIは Referer ヘッダを見て、アプリ登録時の Allowed websites と照合する。
  付けないと 403 REQUEST_CONTEXT_BODY_HTTP_REFERRER_MISSING で全リクエストが落ちる。
  登録値は uchinoko-size.com / *.uchinoko-size.com なので、そのURLを送る。
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional

ENDPOINT = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701"

MIN_INTERVAL_SEC = 1.0      # 申告QPS=1 を守る
MAX_RETRIES = 3             # 第30項: リトライ上限
BACKOFF_BASE_SEC = 2.0
DEFAULT_DAILY_CAP = 1000    # 第30項: 1日の上限。超えたら止まる
DEFAULT_REFERER = "https://uchinoko-size.com/"


class RakutenError(RuntimeError):
    pass


class QuotaExceeded(RakutenError):
    pass


@dataclass(frozen=True)
class Item:
    """掲載に必要な最小限だけを持つ。余計なフィールドは保存しない。"""
    name: str
    price: int
    affiliate_url: str
    shop: str
    item_code: str
    image_url: Optional[str]
    review_count: int
    review_average: float

    @property
    def is_usable(self) -> bool:
        """アフィリエイトURLが取れていない商品は掲載しない。
        素のURLを載せると成果が計上されず、広告表記だけが残ることになる。"""
        return bool(self.affiliate_url) and self.price > 0


def _default_fetch(url: str, referer: str = DEFAULT_REFERER,
                   timeout: float = 15.0) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={
        "User-Agent": "uchinoko-size/1.0",
        "Referer": referer,          # 楽天APIの必須ヘッダ
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status, res.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


class RakutenClient:
    def __init__(self,
                 app_id: Optional[str] = None,
                 access_key: Optional[str] = None,
                 affiliate_id: Optional[str] = None,
                 referer: Optional[str] = None,
                 fetch: Callable[..., tuple[int, str]] = _default_fetch,
                 daily_cap: int = DEFAULT_DAILY_CAP,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic):
        self.app_id = app_id or os.environ.get("RAKUTEN_APP_ID", "")
        self.access_key = access_key or os.environ.get("RAKUTEN_ACCESS_KEY", "")
        self.affiliate_id = affiliate_id or os.environ.get("RAKUTEN_AFFILIATE_ID", "")
        # Allowed websites に登録したドメインと一致している必要がある
        self.referer = (referer
                        or os.environ.get("RAKUTEN_REFERER")
                        or os.environ.get("WP_URL")
                        or DEFAULT_REFERER)
        if not self.app_id or not self.access_key:
            raise RakutenError(
                "RAKUTEN_APP_ID と RAKUTEN_ACCESS_KEY が設定されていません。"
                "GitHub Secrets に登録してください。")

        self._fetch = fetch
        self._sleep = sleep
        self._clock = clock
        self.daily_cap = daily_cap
        self.calls = 0
        self._last_call_at: Optional[float] = None

    # --- 内部 --------------------------------------------------------

    def _throttle(self) -> None:
        if self._last_call_at is None:
            return
        wait = MIN_INTERVAL_SEC - (self._clock() - self._last_call_at)
        if wait > 0:
            self._sleep(wait)

    def _build_url(self, params: dict) -> str:
        q = {
            "applicationId": self.app_id,
            "accessKey": self.access_key,
            "format": "json",
            "formatVersion": "2",
        }
        if self.affiliate_id:
            q["affiliateId"] = self.affiliate_id
        q.update({k: v for k, v in params.items() if v is not None})
        return ENDPOINT + "?" + urllib.parse.urlencode(q)

    def _call(self, params: dict) -> dict:
        if self.calls >= self.daily_cap:
            raise QuotaExceeded(
                f"楽天APIの日次上限 {self.daily_cap} 件に達したため停止しました。")

        url = self._build_url(params)
        last_err = ""

        for attempt in range(MAX_RETRIES):
            self._throttle()
            status, body = self._fetch(url, self.referer)
            self._last_call_at = self._clock()
            self.calls += 1

            if status == 200:
                try:
                    return json.loads(body)
                except json.JSONDecodeError as e:
                    raise RakutenError(f"レスポンスがJSONではありません: {e}") from e

            # 429 / 5xx は時間をおけば回復しうる。それ以外は即座に諦める
            if status == 429 or 500 <= status < 600:
                last_err = f"HTTP {status}: {body[:200]}"
                if attempt < MAX_RETRIES - 1:
                    self._sleep(BACKOFF_BASE_SEC * (2 ** attempt))
                continue

            raise RakutenError(f"HTTP {status}: {body[:300]}")

        raise RakutenError(f"リトライ上限に達しました。{last_err}")

    # --- 公開API ----------------------------------------------------

    def search(self, keyword: str, hits: int = 10,
               min_price: Optional[int] = None,
               max_price: Optional[int] = None,
               sort: str = "-reviewCount") -> list[Item]:
        """商品を検索して、掲載可能なものだけを返す。"""
        data = self._call({
            "keyword": keyword,
            "hits": max(1, min(hits, 30)),
            "minPrice": min_price,
            "maxPrice": max_price,
            "sort": sort,
            "imageFlag": 1,          # 画像のない商品は比較表で使えない
        })
        return [i for i in (self._to_item(r) for r in data.get("Items", []))
                if i.is_usable]

    @staticmethod
    def _to_item(row: dict) -> Item:
        # formatVersion=2 では Items の各要素がそのまま商品オブジェクトになる
        r = row.get("Item", row)
        return Item(
            name=r.get("itemName", ""),
            price=int(r.get("itemPrice") or 0),
            affiliate_url=r.get("affiliateUrl") or "",
            shop=r.get("shopName", ""),
            item_code=r.get("itemCode", ""),
            image_url=(r.get("mediumImageUrls") or [None])[0]
                      if isinstance(r.get("mediumImageUrls"), list) else None,
            review_count=int(r.get("reviewCount") or 0),
            review_average=float(r.get("reviewAverage") or 0.0),
        )


def selftest() -> int:
    """認証情報が通るかだけを確認する。GitHub Actions の初回実行で走らせる。"""
    try:
        client = RakutenClient()
        items = client.search("犬服 小型犬", hits=3)
    except RakutenError as e:
        print(f"NG: {e}")
        return 1

    if not items:
        print("NG: 認証は通ったが、掲載可能な商品が0件でした。"
              "affiliateId が正しいか確認してください。")
        return 1

    print(f"OK: {len(items)}件取得。1件目: {items[0].name[:40]}")
    print(f"    価格 {items[0].price}円 / アフィリンク {'あり' if items[0].affiliate_url else 'なし'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(selftest())
