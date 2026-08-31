import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.article import Offer, Source, weight_article  # noqa: E402
from pipeline.publish import (  # noqa: E402
    DEFAULT_STATUS, LintFailed, MAX_RETRIES, PublishError, WordPress,
)
from pipeline.sizing import Dog, Variant, evaluate  # noqa: E402

CREDS = dict(site_url="https://uchinoko-size.com",
             user="editor",
             app_password="abcd EFGH ijkl MNOP")   # 表示時は空白区切りで出る


def _fit(brand, label, ranges, prov="official"):
    v = Variant(1, brand, label, 1, "wear", "low", prov, ranges)
    return evaluate(Dog(neck=23, chest=32, back=24, weight=2.8), v)


FITS = [(_fit("CALULU", "S", {"neck": (21, 23), "chest": (31, 34),
                              "back": (21, 23), "weight": (2.2, 2.8)}),
         Source("CALULU", "https://www.calulu-dogwear.jp/user_data/dogwearsize",
                "2026-08-29"))]
ARTICLE = weight_article(2.8, FITS)


class Fake:
    """WordPress の代わり。ネットワークには出ない。"""
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, method, headers, payload=None, timeout=30.0):
        self.calls.append({
            "url": url, "method": method, "headers": headers,
            "body": json.loads(payload) if payload else None,
        })
        return self.responses.pop(0) if self.responses else (200, "[]")


def post(**over):
    d = {"id": 12, "link": "https://uchinoko-size.com/?p=12", "status": "draft"}
    d.update(over)
    return (200, json.dumps(d))


def wp(fetch, **kw):
    kw.setdefault("sleep", lambda s: None)
    return WordPress(**CREDS, fetch=fetch, **kw)


# --- 認証情報 -------------------------------------------------------

def test_missing_settings_fail_loudly():
    try:
        WordPress(site_url="", user="", app_password="", fetch=Fake())
    except PublishError as e:
        for k in ("WP_URL", "WP_USER", "WP_APP_PASS"):
            assert k in str(e)
    else:
        raise AssertionError("設定なしで動いてはいけない")


def test_application_password_spaces_are_stripped():
    """管理画面は空白区切りで表示する。そのまま貼っても通るようにする。"""
    f = Fake((200, "[]"), post())
    wp(f).publish(ARTICLE)
    auth = f.calls[0]["headers"]["Authorization"]
    decoded = base64.b64decode(auth.split(" ", 1)[1]).decode()
    assert decoded == "editor:abcdEFGHijklMNOP"


def test_db_credentials_are_never_used():
    """自動化はREST API経由のみ。DB情報は使わない。"""
    src = (Path(__file__).resolve().parents[1] / "pipeline" / "publish.py").read_text()
    for word in ("mysql", "DB_PASSWORD", "wp-config"):
        assert word not in src


# --- 校閲ゲート -----------------------------------------------------

def test_lint_failure_blocks_publishing():
    """最後の関門。壊れた記事を公開しない。"""
    broken = weight_article(2.8, FITS, [Offer("x", 100, "https://hb.afl.rakuten.co.jp/a")])
    broken.body = broken.body.replace("本記事は広告を含みます。", "")
    f = Fake()
    try:
        wp(f).publish(broken)
    except LintFailed as e:
        assert "AD_DISCLOSURE" in str(e)
    else:
        raise AssertionError("校閲を通らない記事を公開してはいけない")
    assert f.calls == [], "校閲で止まったらリクエストを1本も出さない"


def test_clean_article_is_published():
    f = Fake((200, "[]"), post())
    r = wp(f).publish(ARTICLE)
    assert r.post_id == 12 and r.created is True


# --- 重複防止 -------------------------------------------------------

def test_existing_slug_is_updated_not_duplicated():
    """毎回新規作成すると重複記事を量産し、それ自体がスパム判定の材料になる。"""
    f = Fake((200, json.dumps([{"id": 99, "slug": ARTICLE.slug}])),
             post(id=99))
    r = wp(f).publish(ARTICLE)
    assert r.created is False and r.post_id == 99
    assert f.calls[1]["url"].endswith("/posts/99")


def test_slug_lookup_comes_first():
    f = Fake((200, "[]"), post())
    wp(f).publish(ARTICLE)
    assert "slug=" in f.calls[0]["url"] and f.calls[0]["method"] == "GET"
    assert "status=any" in f.calls[0]["url"], "下書きの既存記事も見つける"


# --- 公開状態 -------------------------------------------------------

def test_default_status_is_draft(monkeypatch=None):
    import os
    old = os.environ.pop("PUBLISH_STATUS", None)
    try:
        f = Fake((200, "[]"), post())
        wp(f).publish(ARTICLE)
        assert f.calls[1]["body"]["status"] == DEFAULT_STATUS == "draft"
    finally:
        if old is not None:
            os.environ["PUBLISH_STATUS"] = old


def test_status_can_be_set_explicitly():
    f = Fake((200, "[]"), post(status="publish"))
    r = wp(f).publish(ARTICLE, status="publish")
    assert f.calls[1]["body"]["status"] == "publish"
    assert r.status == "publish"


def test_title_slug_and_body_are_sent():
    f = Fake((200, "[]"), post())
    wp(f).publish(ARTICLE)
    body = f.calls[1]["body"]
    assert body["title"] == ARTICLE.title
    assert body["slug"] == ARTICLE.slug
    assert "比較" in body["content"]


# --- 失敗の扱い -----------------------------------------------------

def test_auth_error_is_explained():
    f = Fake((401, '{"code":"incorrect_password"}'))
    try:
        wp(f).publish(ARTICLE)
    except PublishError as e:
        assert "アプリケーション" in str(e)
    else:
        raise AssertionError("401 で例外が出ていない")


def test_server_error_is_retried():
    f = Fake((503, "down"), (200, "[]"), post())
    assert wp(f).publish(ARTICLE).post_id == 12


def test_retry_limit_is_enforced():
    f = Fake(*[(503, "down")] * (MAX_RETRIES + 2))
    try:
        wp(f).publish(ARTICLE)
    except PublishError as e:
        assert "リトライ上限" in str(e)
    else:
        raise AssertionError("無限にリトライしてはいけない")
    assert len(f.calls) == MAX_RETRIES


def test_non_json_response_is_reported():
    f = Fake((200, "<html>maintenance</html>"))
    try:
        wp(f).publish(ARTICLE)
    except PublishError as e:
        assert "JSON" in str(e)
    else:
        raise AssertionError("HTMLを黙って通してはいけない")


def test_falls_back_to_rest_route_when_wp_json_is_404():
    """パーマリンクが「基本」だと /wp-json/ が404になる。?rest_route= に切り替わること。"""
    seen = []

    def fetch(url, method, headers, payload=None, timeout=30.0):
        seen.append(url)
        if "/wp-json/" in url:
            return 404, '{"code":"rest_no_route"}'
        return 200, '{"id": 1, "name": "test"}'

    wp = WordPress(site_url="https://example.com", user="u",
                           app_password="p p p", fetch=fetch, sleep=lambda s: None)
    status, data = wp._call("/users/me")
    assert status == 200
    assert len(seen) == 2
    assert seen[0] == "https://example.com/wp-json/wp/v2/users/me"
    assert seen[1] == "https://example.com/?rest_route=%2Fwp%2Fv2%2Fusers%2Fme"


def test_rest_route_keeps_query_parameters():
    """slug 検索のクエリが ?rest_route= 形式でも落ちないこと。"""
    seen = []

    def fetch(url, method, headers, payload=None, timeout=30.0):
        seen.append(url)
        if "/wp-json/" in url:
            return 404, "{}"
        return 200, "[]"

    wp = WordPress(site_url="https://example.com", user="u",
                           app_password="p", fetch=fetch, sleep=lambda s: None)
    wp.find_by_slug("dog-wear-size-3kg")
    assert "rest_route=%2Fwp%2Fv2%2Fposts" in seen[-1]
    assert "slug=dog-wear-size-3kg" in seen[-1]
    assert seen[-1].count("?") == 1


def test_404_does_not_loop_forever():
    """両方の形式で404なら、リトライを尽くしてエラーになること。"""
    def fetch(url, method, headers, payload=None, timeout=30.0):
        return 404, "not found"

    wp = WordPress(site_url="https://example.com", user="u",
                           app_password="p", fetch=fetch, sleep=lambda s: None)
    try:
        wp._call("/users/me")
    except PublishError:
        return
    raise AssertionError("404 が続いてもエラーにならなかった")
