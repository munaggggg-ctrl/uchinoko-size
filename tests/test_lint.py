import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.lint import ERROR, WARN, lint  # noqa: E402


def rules(text, severity=None):
    return {f.rule for f in lint(text) if severity is None or f.severity == severity}


AFF = '<a href="https://hb.afl.rakuten.co.jp/xyz">楽天で見る</a>'
SPEC = '<p>胴回り 30〜34cm [公式]</p><p>出典: ブランド公式サイズ表（2026年8月取得）</p>'


# --- 広告表記 -------------------------------------------------------

def test_affiliate_without_disclosure_is_error():
    assert "AD_DISCLOSURE" in rules(f"<p>おすすめです</p>{AFF}", ERROR)


def test_affiliate_with_disclosure_passes():
    text = f"<p>本記事は広告を含みます。</p>{AFF}"
    assert "AD_DISCLOSURE" not in rules(text)


def test_disclosure_after_the_link_is_error():
    text = f"{AFF}\n<p>本記事は広告を含みます。</p>"
    assert "AD_DISCLOSURE_POSITION" in rules(text, ERROR)


def test_no_affiliate_needs_no_disclosure():
    assert rules("<p>犬の胴回りの測り方を説明します。</p>") == set()


def test_various_asp_domains_are_detected():
    for url in ("https://px.a8.net/svt/ejp?a=1",
                "https://af.moshimo.com/af/c/click?a_id=1",
                "https://www.amazon.co.jp/dp/B01?tag=koinu-22",
                "https://ck.jp.ap.valuecommerce.com/serv?x=1"):
        assert "AD_DISCLOSURE" in rules(f'<a href="{url}">買う</a>', ERROR), url


# --- 薬機法 ---------------------------------------------------------

def test_efficacy_claims_are_error():
    for bad in ("このサプリで関節が良くなります",
                "皮膚炎が治ります",
                "アレルギーが改善します",
                "着せるだけで病気を防げます",
                "副作用がありません"):
        assert "YAKUJI" in rules(f"<p>{bad}</p>", ERROR), bad


def test_factual_spec_description_passes():
    ok = "<p>撥水加工が施されており、雨の日の散歩でも水を弾きます。</p>"
    assert "YAKUJI" not in rules(ok)


def test_vet_advice_is_error():
    assert "VET_ADVICE" in rules("<p>受診は不要です。様子を見て大丈夫です。</p>", ERROR)


# --- 優良誤認 -------------------------------------------------------

def test_superlative_without_evidence_is_error():
    assert "SUPERLATIVE" in rules("<p>日本一のハーネスです</p>", ERROR)


def test_superlative_with_evidence_is_downgraded_to_warn():
    text = "<p>各社公式サイトの調査では最安値でした（2026年8月時点）</p>"
    assert "SUPERLATIVE" in rules(text, WARN)
    assert "SUPERLATIVE" not in rules(text, ERROR)


def test_absolute_promise_is_error():
    assert "SUPERLATIVE" in rules("<p>このサイズなら必ず合います</p>", ERROR)


# --- 値の出所（第33項）---------------------------------------------

def test_spec_without_provenance_is_error():
    text = "<p>胴回り 30〜34cm</p><p>出典: 公式サイズ表</p>"
    assert "PROVENANCE_MISSING" in rules(text, ERROR)


def test_spec_without_source_is_error():
    text = "<p>胴回り 30〜34cm [公式]</p>"
    assert "SOURCE_MISSING" in rules(text, ERROR)


def test_complete_spec_block_passes():
    assert rules(SPEC) == set()


def test_provenance_detected_via_data_attribute():
    text = '<td data-prov="official">32cm</td><p>胴回り</p><p>出典: 公式サイズ表</p>'
    assert "PROVENANCE_MISSING" not in rules(text)


def test_spec_split_across_table_cells_is_still_detected():
    """表組みでは見出しと数値が別セルに入る。ここを見逃すと出所不明の数値が出る。"""
    html = (
        "<table>\n"
        "  <tr><th>胴回り</th></tr>\n"
        "  <tr><td>30〜34 cm</td></tr>\n"
        "</table>\n"
    )
    assert "PROVENANCE_MISSING" in rules(html, ERROR)
    assert "SOURCE_MISSING" in rules(html, ERROR)


def test_estimated_marker_is_accepted():
    text = "<p>胴回り 30〜34cm [推定]</p><p>出典: 当サイト推定</p>"
    assert "PROVENANCE_MISSING" not in rules(text)


# --- 抑制 -----------------------------------------------------------

def test_suppression_with_reason_works():
    text = ("<!-- lint:allow=YAKUJI 獣医師監修コメントの引用のため -->\n"
            "<blockquote>症状が改善した例もあります</blockquote>")
    assert "YAKUJI" not in rules(text)


def test_suppression_without_reason_is_ignored():
    text = ("<!-- lint:allow=YAKUJI -->\n"
            "<blockquote>症状が改善した例もあります</blockquote>")
    assert "YAKUJI" in rules(text, ERROR)


def test_suppression_does_not_leak_to_other_rules():
    text = ("<!-- lint:allow=YAKUJI 引用のため -->\n"
            "<p>日本一の商品です</p>")
    assert "SUPERLATIVE" in rules(text, ERROR)


# --- 実運用に近い形 -------------------------------------------------

def test_realistic_article_passes():
    article = (
        "<p>本記事は広告を含みます。</p>\n"
        "<h2>胴回り32cmの小型犬に合うサイズ</h2>\n"
        '<table><tr><th>ブランド</th><th>胴回り</th></tr>\n'
        '<tr><td>A社 S</td><td data-prov="official">30〜34 cm</td></tr></table>\n'
        "<p>A社ではSが◎です。胴回りは範囲内（余裕あり）。</p>\n"
        "<p>出典: 各ブランド公式サイズ表（2026年8月取得）</p>\n"
        f"{AFF}\n"
    )
    assert lint(article) == []
