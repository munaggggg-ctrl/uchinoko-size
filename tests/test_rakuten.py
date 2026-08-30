import json
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.rakuten import (  # noqa: E402
    DEFAULT_REFERER, MAX_RETRIES, QuotaExceeded, RakutenClient, RakutenError,
    _default_fetch, _origin_of,
)

CREDS = dict(app_id="app-123", access_key="pk_test", affiliate_id="aa.bb.cc.dd")


def body(*items):
    return json.dumps({"Items": list(items)})


ITEM = {
    "itemName": "小型犬用 タンクトップ",
    "itemPrice": 1980,
    "affiliateUrl": "https://hb.afl.rakuten.co.jp/hgc/xxx/",
    "shopName": "テストショップ",
    "itemCode": "shop:12345",
    "mediumImageUrls": ["https://thumbnail.image.rakuten.co.jp/a.jpg"],
    "reviewCount": 42,
    "reviewAverage": "4.5",
}


class Recorder:
    """ネットワークに出ない差し替え用 fetch。"""
    def __init__(self, *responses):
        self.responses = list(responses)
        self.urls = []
        self.referers = []

    def __call__(self, url, referer=None, timeout=15.0):
        self.urls.append(url)
        self.referers.append(referer)
        return self.responses.pop(0) if self.responses else (200, body())


def client(fetch, **kw):
    kw.setdefault("sleep", lambda s: None)
    return RakutenClient(fetch=fetch, **CREDS, **kw)


def q(url):
    return urllib.parse.parse_qs(urllib.parse.urlparse(url).query)


# --- 認証情報 -------------------------------------------------------

def test_missing_credentials_fail_loudly():
    try:
        RakutenClient(app_id="", access_key="", fetch=Recorder())
    except RakutenError as e:
        assert "GitHub Secrets" in str(e)
    else:
        raise AssertionError("認証情報なしで動いてはいけない")


def test_request_carries_both_app_id_and_access_key():
    """accessKey は 2026-07 版で必須になった。落とすと全リクエストが失敗する。"""
    f = Recorder((200, body(ITEM)))
    client(f).search("犬服")
    p = q(f.urls[0])
    assert p["applicationId"] == ["app-123"]
    assert p["accessKey"] == ["pk_test"]


def test_affiliate_id_is_sent():
    f = Recorder((200, body(ITEM)))
    client(f).search("犬服")
    assert q(f.urls[0])["affiliateId"] == ["aa.bb.cc.dd"]


def test_affiliate_id_is_omitted_when_absent():
    f = Recorder((200, body(ITEM)))
    RakutenClient(app_id="a", access_key="k", affiliate_id="",
                  fetch=f, sleep=lambda s: None).search("犬服")
    assert "affiliateId" not in q(f.urls[0])


# --- 掲載可否 -------------------------------------------------------

def test_items_without_affiliate_url_are_dropped():
    """素のURLを載せると成果が計上されず、広告表記だけが残る。"""
    bad = dict(ITEM, affiliateUrl="")
    f = Recorder((200, body(ITEM, bad)))
    items = client(f).search("犬服")
    assert len(items) == 1


def test_zero_price_items_are_dropped():
    f = Recorder((200, body(dict(ITEM, itemPrice=0))))
    assert client(f).search("犬服") == []


def test_item_fields_are_parsed():
    f = Recorder((200, body(ITEM)))
    it = client(f).search("犬服")[0]
    assert it.name == "小型犬用 タンクトップ"
    assert it.price == 1980
    assert it.review_count == 42 and it.review_average == 4.5
    assert it.image_url.endswith("a.jpg")


# --- レート制限とリトライ（第30項）----------------------------------

def test_throttles_to_one_request_per_second():
    """アプリ登録で Expected QPS = 1 と申告している。申告より速く叩かない。"""
    slept, now = [], [0.0]
    f = Recorder((200, body(ITEM)), (200, body(ITEM)))
    c = RakutenClient(**CREDS, fetch=f,
                      sleep=lambda s: (slept.append(s), now.__setitem__(0, now[0] + s)),
                      clock=lambda: now[0])
    c.search("犬服")
    c.search("ハーネス")
    assert slept and slept[0] >= 1.0


def test_retries_on_rate_limit_then_succeeds():
    f = Recorder((429, "too many"), (200, body(ITEM)))
    assert len(client(f).search("犬服")) == 1
    assert len(f.urls) == 2


def test_retries_on_server_error():
    f = Recorder((503, "unavailable"), (503, "unavailable"), (200, body(ITEM)))
    assert len(client(f).search("犬服")) == 1


def test_gives_up_after_the_retry_limit():
    f = Recorder(*[(503, "down")] * (MAX_RETRIES + 2))
    try:
        client(f).search("犬服")
    except RakutenError as e:
        assert "リトライ上限" in str(e)
    else:
        raise AssertionError("無限にリトライしてはいけない")
    assert len(f.urls) == MAX_RETRIES


def test_client_errors_are_not_retried():
    """401/400 は待っても直らない。叩き続けるとアカウントに不利になる。"""
    f = Recorder((401, "unauthorized"))
    try:
        client(f).search("犬服")
    except RakutenError as e:
        assert "401" in str(e)
    else:
        raise AssertionError("4xx で例外が出ていない")
    assert len(f.urls) == 1


def test_daily_cap_stops_the_run():
    f = Recorder(*[(200, body(ITEM))] * 5)
    c = client(f, daily_cap=2)
    c.search("a")
    c.search("b")
    try:
        c.search("c")
    except QuotaExceeded as e:
        assert "日次上限" in str(e)
    else:
        raise AssertionError("日次上限が効いていない")


# --- 入力の健全性 ---------------------------------------------------

def test_hits_is_clamped_to_the_api_maximum():
    f = Recorder((200, body(ITEM)))
    client(f).search("犬服", hits=999)
    assert q(f.urls[0])["hits"] == ["30"]


def test_none_parameters_are_not_sent():
    f = Recorder((200, body(ITEM)))
    client(f).search("犬服", min_price=None)
    assert "minPrice" not in q(f.urls[0])


def test_malformed_json_is_reported_clearly():
    f = Recorder((200, "<html>maintenance</html>"))
    try:
        client(f).search("犬服")
    except RakutenError as e:
        assert "JSON" in str(e)
    else:
        raise AssertionError("壊れたレスポンスを黙って通してはいけない")


# --- Referer（2026-08-30 に判明した必須ヘッダ）--------------------------

def test_referer_is_sent():
    """楽天APIは Referer を見てアプリ登録の Allowed websites と照合する。
    付け忘れると 403 REQUEST_CONTEXT_BODY_HTTP_REFERRER_MISSING で全滅する。"""
    f = Recorder((200, body(ITEM)))
    client(f).search("犬服")
    assert f.referers[0] == DEFAULT_REFERER


def test_referer_can_be_overridden():
    f = Recorder((200, body(ITEM)))
    RakutenClient(**CREDS, referer="https://example.com/", fetch=f,
                  sleep=lambda s: None).search("犬服")
    assert f.referers[0] == "https://example.com/"


def test_referer_always_ends_with_a_path():
    """楽天が受け付けたのはブラウザが送る形（末尾スラッシュ付き）だった。
    スラッシュなしで送ると 403 REQUEST_CONTEXT_BODY_HTTP_REFERRER_MISSING になる可能性がある。"""
    f = Recorder((200, body(ITEM)))
    RakutenClient(**CREDS, referer="https://example.com", fetch=f,
                  sleep=lambda s: None).search("犬服")
    assert f.referers[0] == "https://example.com/"


def test_referer_falls_back_to_site_url(monkeypatch=None):
    import os
    old = os.environ.get("WP_URL")
    os.environ["WP_URL"] = "https://uchinoko-size.com"
    try:
        f = Recorder((200, body(ITEM)))
        RakutenClient(**CREDS, fetch=f, sleep=lambda s: None).search("犬服")
        # 末尾スラッシュは補われる（ブラウザが送る形にそろえるため）
        assert f.referers[0] == "https://uchinoko-size.com/"
    finally:
        if old is None:
            os.environ.pop("WP_URL", None)
        else:
            os.environ["WP_URL"] = old


def test_default_referer_matches_the_registered_domain():
    """アプリ登録の Allowed websites は uchinoko-size.com。ここがずれると403になる。"""
    assert "uchinoko-size.com" in DEFAULT_REFERER


def test_origin_is_derived_from_referer():
    """Referer だけでは 403 になる。Origin も必要（2026-08-30 に実測で確定）。"""
    assert _origin_of("https://uchinoko-size.com/") == "https://uchinoko-size.com"
    assert _origin_of("https://uchinoko-size.com/size/chihuahua/") == "https://uchinoko-size.com"
    assert _origin_of("http://example.com/a/b") == "http://example.com"


def test_both_referer_and_origin_headers_are_sent():
    """ここが欠けると全リクエストが 403 になる。実装の中心。"""
    sent = {}

    class FakeReq:
        def __init__(self, url, headers=None):
            sent.update(headers or {})

    import urllib.request as ur
    real_req, real_open = ur.Request, ur.urlopen

    class FakeRes:
        status = 200
        def read(self): return b'{"Items":[]}'
        def __enter__(self): return self
        def __exit__(self, *a): return False

    ur.Request = FakeReq
    ur.urlopen = lambda req, timeout=None: FakeRes()
    try:
        _default_fetch("https://example.com/api", "https://uchinoko-size.com/")
    finally:
        ur.Request, ur.urlopen = real_req, real_open

    assert sent.get("Referer") == "https://uchinoko-size.com/"
    assert sent.get("Origin") == "https://uchinoko-size.com"
