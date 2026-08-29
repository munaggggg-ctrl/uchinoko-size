import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.collect import (  # noqa: E402
    CollectError, Extraction, GeminiExtractor, QuotaExceeded,
    MAX_RETRIES, to_sql, validate,
)

GOOD = {
    "brand_name": "テストブランド",
    "category": "wear",
    "measure_basis": "dog_fit_range",
    "basis_quote": "サイズ表はワンちゃんのボディサイズです。洋服のサイズではありません。",
    "stretch": "low",
    "sizes": [
        {"label": "S", "neck_min": 21, "neck_max": 23, "chest_min": 31,
         "chest_max": 34, "back_min": 21, "back_max": 23,
         "weight_min": 2.2, "weight_max": 2.8},
        {"label": "M", "neck_min": 24, "neck_max": 27, "chest_min": 35,
         "chest_max": 38, "back_min": 24, "back_max": 26,
         "weight_min": 2.8, "weight_max": 3.8},
    ],
}


def ex(**over):
    d = json.loads(json.dumps(GOOD))
    d.update(over)
    return Extraction.from_dict(d)


def reasons(e):
    return {r.reason for r in validate(e)}


# --- 検証ゲート: ここがこのモジュールの中心 -------------------------

def test_good_extraction_passes():
    assert validate(ex()) == []


def test_missing_measure_basis_is_rejected():
    """『犬の実測』か『服の実寸』か不明なまま保存すると全推薦が壊れる。"""
    assert "basis_unknown" in reasons(ex(measure_basis=None))


def test_measure_basis_without_a_quote_is_rejected():
    """根拠の原文が取れていない＝モデルの推測。保存しない。"""
    assert "basis_quote_missing" in reasons(ex(basis_quote=None))


def test_too_short_quote_is_rejected():
    assert "basis_quote_missing" in reasons(ex(basis_quote="犬"))


def test_garment_actual_with_quote_passes():
    assert validate(ex(
        measure_basis="garment_actual",
        basis_quote="サイズ表の数字は全てお洋服の仕上り寸法となっております。")) == []


# --- 数値の健全性 ---------------------------------------------------

def test_inverted_range_is_rejected():
    e = ex(sizes=[dict(GOOD["sizes"][0], chest_min=40, chest_max=30)])
    assert "range_inverted" in reasons(e)


def test_implausible_value_is_rejected():
    """読み取り誤り（桁ずれ・単位違い）を止める。"""
    e = ex(sizes=[dict(GOOD["sizes"][0], chest_max=350)])
    assert "value_implausible" in reasons(e)


def test_row_with_no_numbers_is_rejected():
    assert "row_empty" in reasons(ex(sizes=[{"label": "S"}]))


def test_duplicate_labels_are_rejected():
    e = ex(sizes=[GOOD["sizes"][0], dict(GOOD["sizes"][1], label="S")])
    assert "label_duplicated" in reasons(e)


def test_missing_label_is_rejected():
    e = ex(sizes=[dict(GOOD["sizes"][0], label="")])
    assert "label_missing" in reasons(e)


def test_empty_result_is_rejected():
    assert "no_rows" in reasons(ex(sizes=[]))


def test_partial_rows_are_allowed():
    """記載のない項目は null のまま通す。0で埋めさせない。"""
    e = ex(sizes=[{"label": "S", "chest_min": 31, "chest_max": 34}])
    assert validate(e) == []


# --- SQL 生成 -------------------------------------------------------

def test_sql_is_not_generated_for_invalid_extraction():
    try:
        to_sql(ex(measure_basis=None), "t", "https://e.com", "2026-08-29", 1, 1, 1)
    except CollectError as e:
        assert "検証を通っていない" in str(e)
    else:
        raise AssertionError("検証を通らない抽出からSQLを作ってはいけない")


def test_sql_contains_the_basis_quote_and_source():
    sql = to_sql(ex(), "test", "https://example.com/size", "2026-08-29T10:00:00+09:00",
                 9, 9, 9)
    assert "dog_fit_range" in sql
    assert "ワンちゃんのボディサイズ" in sql, "判定根拠の原文がSQLに残ること"
    assert "https://example.com/size" in sql
    assert "'official'" in sql


def test_sql_column_order_matches_the_schema():
    sql = to_sql(ex(), "test", "https://e.com", "2026-08-29", 9, 9, 9)
    head = sql[sql.index("INSERT INTO size_variant"):]
    cols = head[head.index("(") + 1:head.index(")")].split(",")
    assert [c.strip() for c in cols][3:11] == [
        "neck_min", "neck_max", "chest_min", "chest_max",
        "back_min", "back_max", "weight_min", "weight_max"]
    assert "(9,'S',1,21,23,31,34,21,23,2.2,2.8,'official',9)" in sql


def test_sql_escapes_quotes():
    sql = to_sql(ex(brand_name="O'Brien"), "ob", "https://e.com", "2026-08-29", 1, 1, 1)
    assert "O''Brien" in sql


def test_null_is_used_for_missing_values():
    e = ex(sizes=[{"label": "S", "chest_min": 31, "chest_max": 34}])
    sql = to_sql(e, "t", "https://e.com", "2026-08-29", 1, 1, 1)
    assert "NULL,NULL,31,34,NULL,NULL,NULL,NULL" in sql, "0で埋めない"


# --- API クライアント -----------------------------------------------

def envelope(payload):
    return json.dumps({"candidates": [{"content": {"parts": [
        {"text": json.dumps(payload)}]}}]})


class Recorder:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, payload, timeout=60.0):
        self.calls.append((url, json.loads(payload)))
        return self.responses.pop(0) if self.responses else (200, envelope(GOOD))


def client(fetch, **kw):
    kw.setdefault("sleep", lambda s: None)
    return GeminiExtractor(api_key="k", fetch=fetch, **kw)


def test_missing_api_key_fails_loudly():
    try:
        GeminiExtractor(api_key="", fetch=Recorder())
    except CollectError as e:
        assert "GEMINI_API_KEY" in str(e)
    else:
        raise AssertionError("鍵なしで動いてはいけない")


def test_text_extraction_round_trip():
    f = Recorder((200, envelope(GOOD)))
    out = client(f).extract(text="<table>...</table>")
    assert out.brand_name == "テストブランド"
    assert len(out.sizes) == 2
    assert validate(out) == []


def test_image_is_sent_as_inline_data():
    """サイズ表を画像で載せているブランドが相当数ある。ここが要件。"""
    f = Recorder((200, envelope(GOOD)))
    client(f).extract(image=("image/png", b"\x89PNG-fake"))
    parts = f.calls[0][1]["contents"][0]["parts"]
    inline = [p for p in parts if "inline_data" in p]
    assert len(inline) == 1
    assert inline[0]["inline_data"]["mime_type"] == "image/png"
    assert inline[0]["inline_data"]["data"], "base64で本文が入っていること"


def test_temperature_is_zero():
    """読み取り作業なので揺らがせない。"""
    f = Recorder((200, envelope(GOOD)))
    client(f).extract(text="x")
    assert f.calls[0][1]["generationConfig"]["temperature"] == 0


def test_nothing_to_extract_is_an_error():
    try:
        client(Recorder()).extract()
    except CollectError:
        pass
    else:
        raise AssertionError("入力なしで呼べてはいけない")


def test_retries_on_rate_limit():
    f = Recorder((429, "slow down"), (200, envelope(GOOD)))
    assert client(f).extract(text="x").brand_name == "テストブランド"
    assert len(f.calls) == 2


def test_gives_up_after_the_retry_limit():
    f = Recorder(*[(503, "down")] * (MAX_RETRIES + 2))
    try:
        client(f).extract(text="x")
    except CollectError as e:
        assert "リトライ上限" in str(e)
    else:
        raise AssertionError("無限にリトライしてはいけない")
    assert len(f.calls) == MAX_RETRIES


def test_client_errors_are_not_retried():
    f = Recorder((400, "bad request"))
    try:
        client(f).extract(text="x")
    except CollectError as e:
        assert "400" in str(e)
    else:
        raise AssertionError("4xx で例外が出ていない")
    assert len(f.calls) == 1


def test_daily_cap_stops_the_run():
    f = Recorder(*[(200, envelope(GOOD))] * 5)
    c = client(f, daily_cap=2)
    c.extract(text="a"); c.extract(text="b")
    try:
        c.extract(text="c")
    except QuotaExceeded as e:
        assert "日次上限" in str(e)
    else:
        raise AssertionError("日次上限が効いていない")


def test_throttles_between_calls():
    slept, now = [], [0.0]
    f = Recorder((200, envelope(GOOD)), (200, envelope(GOOD)))
    c = GeminiExtractor(api_key="k", fetch=f,
                        sleep=lambda s: (slept.append(s), now.__setitem__(0, now[0] + s)),
                        clock=lambda: now[0])
    c.extract(text="a"); c.extract(text="b")
    assert slept and slept[0] >= 4.0, "無料枠のレート制限を守る"


def test_malformed_envelope_is_reported():
    f = Recorder((200, json.dumps({"candidates": []})))
    try:
        client(f).extract(text="x")
    except CollectError as e:
        assert "想定外のレスポンス構造" in str(e)
    else:
        raise AssertionError("壊れたレスポンスを黙って通してはいけない")


def test_non_json_payload_is_reported():
    f = Recorder((200, json.dumps({"candidates": [{"content": {"parts": [
        {"text": "すみません、読み取れませんでした"}]}}]})))
    try:
        client(f).extract(text="x")
    except CollectError as e:
        assert "JSONとして読めません" in str(e)
    else:
        raise AssertionError("JSON以外を黙って通してはいけない")
