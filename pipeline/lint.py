"""
公開前の校閲linter.

ここをLLMにやらせない理由:
  「PR表記があるか」「『治る』と書いていないか」「公式値と推定値が区別されているか」は
  正規表現で100%判定できる。LLMは95%しか判定できず、毎回違う5%を見逃す。
  法令リスクのある工程を確率的な仕組みに任せるのは設計ミス。

使い方:
  python -m pipeline.lint path/to/article.html [...]
  終了コード 0 = 公開可 / 1 = ERROR あり（GitHub Actions が公開を止める）

抑制:
  どうしても必要な箇所は直前の行に
    <!-- lint:allow=RULE_ID 理由 -->
  を書く。理由は必須。理由なしの抑制は抑制として扱わない。
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

ERROR = "ERROR"
WARN = "WARN"


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str
    line: int
    excerpt: str
    message: str
    hint: str

    def format(self, path: str) -> str:
        return (f"{path}:{self.line}: {self.severity} [{self.rule}] {self.message}\n"
                f"    > {self.excerpt}\n"
                f"    → {self.hint}")


# =====================================================================
# 1. アフィリエイト広告表記（景品表示法 / ステマ規制）
# =====================================================================

AFFILIATE_SIGNS = re.compile(
    r"(hb\.afl\.rakuten\.co\.jp|a8\.net|px\.a8\.net|af\.moshimo\.com"
    r"|amazon\.co\.jp/[^\"'\s]*tag=|ck\.jp\.ap\.valuecommerce\.com"
    r"|class=[\"'][^\"']*\baff\b)",
    re.I,
)

# 消費者庁の運用上、一般消費者が広告と判別できる表記であること
AD_DISCLOSURE = re.compile(
    r"(広告を含みます|広告が含まれます|アフィリエイト(広告|リンク)を含"
    r"|本記事はプロモーションを含|PR表記|\bPR\b|\[PR\]|＃PR|#PR)"
)


# =====================================================================
# 2. 薬機法（獣医療・効能効果の標榜）
#    このメディアは買い物メディアであり、効能を述べる立場にない（引継書 第32項）
# =====================================================================

YAKUJI = re.compile(
    r"(治りま|治る|完治|治療でき|effective|予防でき|予防に効"
    r"|症状が(改善|緩和)し|痛みが(取れ|消え)|関節が良くな"
    r"|免疫力が(上が|高ま)|アレルギーが(治|改善)"
    r"|病気(を|が)(防げ|治)|医薬品と同等|副作用がありません)"
)

# 診断・投薬に踏み込む記述
VET_ADVICE = re.compile(
    r"(投薬(すべき|してください)|診断(できます|されます)"
    r"|受診(は不要|しなくて)|様子を見て(大丈夫|問題ありません))"
)


# =====================================================================
# 3. 優良誤認・最上級表現（景品表示法 第5条）
#    根拠の併記なしに使えない語
# =====================================================================

SUPERLATIVE = re.compile(
    r"(日本一|世界一|No\.?1|ナンバーワン|業界最安|最安値|最高級"
    r"|完全に安全|絶対に(安全|大丈夫|失敗しません)|必ず(合います|痩せ|治)"
    r"|唯一の|他社より優れ)"
)

# 根拠の併記があれば WARN に落とす
EVIDENCE_NEARBY = re.compile(r"(出典|調査|各社公式サイト|\d{4}年\d{1,2}月時点|当社調べ)")


# =====================================================================
# 4. 数値の出所（引継書 第33項：公式値・AI推定値・ユーザー投稿値を分離する）
# =====================================================================

# 寸法・体重の数値表現
SPEC_KEYWORD = re.compile(r"(首回り|胴回り|着丈|背丈|対応体重|推奨体重|耐荷重|外寸|内寸)")
SPEC_NUMBER = re.compile(
    SPEC_KEYWORD.pattern + r"[^。]{0,40}?\d+(\.\d+)?\s*(cm|kg|センチ|キロ)"
)

# 種別マーカー。DBの provenance と対応させる
PROV_MARKER = re.compile(
    r"(data-prov=[\"'](official|estimated|user)[\"']"
    r"|\[公式\]|\[メーカー公式\]|\[推定\]|\[AI推定\]|\[ユーザー実績\]"
    r"|メーカー公式値|当サイト推定|ユーザー投稿値)"
)

SOURCE_LINK = re.compile(r"(出典|参照元|公式サイズ表|<a[^>]+rel=[\"']nofollow)")


# =====================================================================

ALLOW = re.compile(r"<!--\s*lint:allow=([A-Z_]+)\s+(\S[^>]*?)-->")


TAG = re.compile(r"<[^>]*>")


def _strip_tags(s: str) -> str:
    """HTMLのタグを空白に潰す。表組みでは見出しと数値が別セルに入るため、
    タグを残したままだと『首回り … 22cm』を1つの記述として拾えない。"""
    return TAG.sub(" ", s)


def _lines(text: str) -> list[str]:
    return text.split("\n")


def _suppressed(lines: list[str], idx: int, rule: str) -> bool:
    """直前2行以内に理由つきの抑制コメントがあるか。"""
    for j in range(max(0, idx - 2), idx):
        m = ALLOW.search(lines[j])
        if m and m.group(1) == rule and m.group(2).strip():
            return True
    return False


def _excerpt(line: str, limit: int = 90) -> str:
    s = re.sub(r"\s+", " ", line).strip()
    return s[:limit] + ("…" if len(s) > limit else "")


def lint(text: str) -> list[Finding]:
    lines = _lines(text)
    # 表組み対応: 行内のタグを潰した版を、スペック検出だけに使う
    flat_lines = [_strip_tags(l) for l in lines]
    flat_text = _strip_tags(text.replace("\n", " \n "))
    out: list[Finding] = []

    def add(rule, sev, i, msg, hint):
        if not _suppressed(lines, i, rule):
            out.append(Finding(rule, sev, i + 1, _excerpt(lines[i]), msg, hint))

    # --- 文書全体で1回判定するもの -----------------------------------
    has_affiliate = bool(AFFILIATE_SIGNS.search(text))
    has_disclosure = bool(AD_DISCLOSURE.search(text))

    if has_affiliate and not has_disclosure:
        i = next((k for k, l in enumerate(lines) if AFFILIATE_SIGNS.search(l)), 0)
        out.append(Finding(
            "AD_DISCLOSURE", ERROR, i + 1, _excerpt(lines[i]),
            "アフィリエイトリンクがあるのに広告表記がありません（景品表示法・ステマ規制）",
            "本文の冒頭に「本記事は広告を含みます」を入れてください",
        ))

    if has_disclosure and has_affiliate:
        # 表記が末尾にしかない場合、一般消費者が判別できるとは言い難い
        first_ad = next(k for k, l in enumerate(lines) if AD_DISCLOSURE.search(l))
        first_link = next(k for k, l in enumerate(lines) if AFFILIATE_SIGNS.search(l))
        if first_ad > first_link:
            out.append(Finding(
                "AD_DISCLOSURE_POSITION", ERROR, first_ad + 1, _excerpt(lines[first_ad]),
                "広告表記が最初のアフィリエイトリンクより後ろにあります",
                "表記はリンクより前、記事冒頭に置いてください",
            ))

    # 表組みでは見出しと数値が別の行・別のセルに入るので、文書全体の平坦化テキストで判定する
    has_spec = bool(SPEC_NUMBER.search(flat_text))

    def _spec_line() -> int:
        for k, fl in enumerate(flat_lines):
            if SPEC_NUMBER.search(fl) or SPEC_KEYWORD.search(fl):
                return k
        return 0

    if has_spec and not PROV_MARKER.search(text):
        i = _spec_line()
        out.append(Finding(
            "PROVENANCE_MISSING", ERROR, i + 1, _excerpt(lines[i]),
            "寸法・体重の数値があるのに、値の種別（公式/推定/ユーザー）が示されていません",
            "data-prov 属性か [公式]/[推定] の明示を付けてください（引継書 第33項）",
        ))

    if has_spec and not SOURCE_LINK.search(text):
        i = _spec_line()
        out.append(Finding(
            "SOURCE_MISSING", ERROR, i + 1, _excerpt(lines[i]),
            "スペック数値があるのに出典がありません",
            "ブランド公式サイズ表へのリンクと取得日を併記してください",
        ))

    # --- 行ごとの判定 -------------------------------------------------
    for i, line in enumerate(lines):
        if YAKUJI.search(line):
            add("YAKUJI", ERROR, i,
                "薬機法に触れうる効能・効果の表現です",
                "商品の効能は述べず、仕様と使用感の事実にとどめてください")

        if VET_ADVICE.search(line):
            add("VET_ADVICE", ERROR, i,
                "診断・投薬・受診要否への踏み込みです（引継書 第32項）",
                "獣医師への相談を促す表現に置き換えてください")

        if SUPERLATIVE.search(line):
            sev = WARN if EVIDENCE_NEARBY.search(line) else ERROR
            add("SUPERLATIVE", sev, i,
                "根拠の併記が必要な最上級・断定表現です（景品表示法）",
                "調査範囲と時点を併記するか、表現を弱めてください")

    return out


def lint_file(path: Path) -> list[Finding]:
    return lint(path.read_text(encoding="utf-8"))


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: python -m pipeline.lint FILE [FILE...]", file=sys.stderr)
        return 2

    errors = warns = 0
    for arg in argv:
        p = Path(arg)
        if not p.exists():
            print(f"{arg}: ファイルがありません", file=sys.stderr)
            return 2
        for f in lint_file(p):
            print(f.format(str(p)))
            if f.severity == ERROR:
                errors += 1
            else:
                warns += 1

    total = errors + warns
    if total == 0:
        print(f"校閲OK: {len(argv)}件、指摘なし")
    else:
        print(f"\n指摘 {total}件（ERROR {errors} / WARN {warns}）")
    if errors:
        print("ERROR があるため公開を中止します。")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
