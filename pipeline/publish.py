"""
WordPress への投稿。

設計:
  WordPress の REST API を、アプリケーションパスワードで叩く。
  管理者パスワードもDB接続情報も使わない。アプリケーションパスワードは
  権限を絞れて、漏れても管理画面から1クリックで失効できる（引継書 第34項）。

安全装置:
  1. 公開の直前にもう一度 lint を通す。ワークフロー側でも通しているが、
     ここが最後の関門なので二重に掛ける。ERROR があれば投稿しない。
  2. slug で既存記事を探し、あれば更新する。毎回新規作成して重複記事を
     量産すると、それ自体がスパム判定の材料になる（引継書 第31項）。
  3. 既定は下書き。自動公開は PUBLISH_STATUS=publish を明示したときだけ。
     壊れたものを無人で公開し続ける事故のほうが、公開が1日遅れるより高くつく。
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional

from .article import Article
from .lint import ERROR, lint

MAX_RETRIES = 3
BACKOFF_BASE_SEC = 2.0
DEFAULT_STATUS = "draft"


class PublishError(RuntimeError):
    pass


class LintFailed(PublishError):
    """校閲で ERROR が出た。公開してはいけない。"""


@dataclass(frozen=True)
class Published:
    post_id: int
    url: str
    status: str
    created: bool          # 新規作成なら True、既存の更新なら False


def _default_fetch(url: str, method: str, headers: dict,
                   payload: Optional[bytes] = None,
                   timeout: float = 30.0) -> tuple[int, str]:
    req = urllib.request.Request(url, data=payload, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status, res.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


class WordPress:
    def __init__(self,
                 site_url: Optional[str] = None,
                 user: Optional[str] = None,
                 app_password: Optional[str] = None,
                 fetch: Callable[..., tuple[int, str]] = _default_fetch,
                 sleep: Callable[[float], None] = time.sleep):
        self.site_url = (site_url or os.environ.get("WP_URL", "")).rstrip("/")
        self.user = user or os.environ.get("WP_USER", "")
        # アプリケーションパスワードは表示時に空白区切りになっている。空白は無視される
        raw = app_password if app_password is not None else os.environ.get("WP_APP_PASS", "")
        self.app_password = raw.replace(" ", "")

        missing = [n for n, v in (("WP_URL", self.site_url),
                                  ("WP_USER", self.user),
                                  ("WP_APP_PASS", self.app_password)) if not v]
        if missing:
            raise PublishError(
                f"{' / '.join(missing)} が設定されていません。GitHub Secrets に登録してください。")

        self._fetch = fetch
        self._sleep = sleep
        # "pretty" = /wp-json/... 、"query" = /?rest_route=... （パーマリンクが「基本」の環境）
        self._rest_style = os.environ.get("WP_REST_STYLE", "pretty")

    # --- 内部 -------------------------------------------------------

    @property
    def _auth(self) -> str:
        token = base64.b64encode(
            f"{self.user}:{self.app_password}".encode()).decode("ascii")
        return f"Basic {token}"

    def _url(self, path: str) -> str:
        """REST のURLを組み立てる。

        パーマリンク設定が「基本」のままだと /wp-json/ は 404 を返す。
        その環境でも動くように ?rest_route= 形式へ切り替えられるようにしてある。
        """
        if self._rest_style == "pretty":
            return f"{self.site_url}/wp-json/wp/v2{path}"
        route, _, qs = path.partition("?")
        url = f"{self.site_url}/?" + urllib.parse.urlencode(
            {"rest_route": f"/wp/v2{route}"})
        return f"{url}&{qs}" if qs else url

    def _call(self, path: str, method: str = "GET",
              body: Optional[dict] = None) -> tuple[int, object]:
        url = self._url(path)
        headers = {
            "Authorization": self._auth,
            "User-Agent": "uchinoko-size/1.0",
            "Accept": "application/json",
        }
        payload = None
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        last = ""
        for attempt in range(MAX_RETRIES):
            status, text = self._fetch(url, method, headers, payload)

            if 200 <= status < 300:
                try:
                    return status, json.loads(text) if text.strip() else {}
                except json.JSONDecodeError as e:
                    raise PublishError(
                        f"WordPress の応答がJSONではありません（{status}）: {text[:200]}") from e

            if status == 429 or 500 <= status < 600:
                last = f"HTTP {status}: {text[:200]}"
                if attempt < MAX_RETRIES - 1:
                    self._sleep(BACKOFF_BASE_SEC * (2 ** attempt))
                continue

            if status == 404 and self._rest_style == "pretty":
                # パーマリンクが「基本」の環境。?rest_route= 形式へ切り替えて張り直す。
                self._rest_style = "query"
                url = self._url(path)
                continue

            if status in (401, 403):
                raise PublishError(
                    f"認証に失敗しました（HTTP {status}）。WP_USER とアプリケーション"
                    f"パスワードを確認してください: {text[:200]}")
            raise PublishError(f"HTTP {status}: {text[:300]}")

        raise PublishError(f"リトライ上限に達しました。{last}")

    def find_by_slug(self, slug: str, endpoint: str = "posts") -> Optional[dict]:
        """同じ slug の記事を探す。重複記事を作らないために必ず先に引く。"""
        q = urllib.parse.urlencode({"slug": slug, "status": "any", "per_page": 1})
        _, data = self._call(f"/{endpoint}?{q}")
        if isinstance(data, list) and data:
            return data[0]
        return None

    # --- 公開 -------------------------------------------------------

    def publish(self, article: Article, status: Optional[str] = None,
                endpoint: str = "posts") -> Published:
        """endpoint="pages" にすると固定ページとして出す。
        診断ツールは記事ではなく道具なので、1枚の固定ページを上書きし続ける。"""
        problems = [f for f in lint(article.body) if f.severity == ERROR]
        if problems:
            raise LintFailed(
                "校閲で ERROR が出たため公開を中止しました: "
                + "; ".join(f"{f.rule}(L{f.line})" for f in problems))

        status = status or os.environ.get("PUBLISH_STATUS", DEFAULT_STATUS)
        body = {
            "title": article.title,
            "slug": article.slug,
            "content": article.body,
            "status": status,
        }

        existing = self.find_by_slug(article.slug, endpoint)
        if existing:
            _, data = self._call(f"/{endpoint}/{existing['id']}", "POST", body)
            created = False
        else:
            _, data = self._call(f"/{endpoint}", "POST", body)
            created = True

        return Published(post_id=int(data["id"]),
                         url=data.get("link", ""),
                         status=data.get("status", status),
                         created=created)


def selftest() -> int:
    """接続確認だけ。記事は投稿しない。"""
    try:
        wp = WordPress()
        status, me = wp._call("/users/me")
    except PublishError as e:
        print(f"NG: {e}")
        return 1
    name = me.get("name") if isinstance(me, dict) else "?"
    print(f"OK: {wp.site_url} に接続できました（ユーザー: {name}）")
    print(f"    既定の公開状態: {os.environ.get('PUBLISH_STATUS', DEFAULT_STATUS)}")
    return 0


def publish_tool_page(wp: "WordPress") -> int:
    """診断ツールの固定ページを1枚、同じ slug に上書きし続ける。"""
    from .toolpage import ToolPageError, build_tool_page
    try:
        article = build_tool_page()
    except ToolPageError as e:
        print(f"NG: 診断ページを組み立てられません: {e}")
        return 1
    try:
        res = wp.publish(article, endpoint="pages")
    except LintFailed as e:
        print(f"NG: {e}")
        return 1
    except PublishError as e:
        print(f"NG: {e}")
        return 1
    verb = "作成" if res.created else "更新"
    print(f"publish: 固定ページを{verb}しました id={res.post_id} status={res.status}")
    print(f"    {res.url}")
    return 0


def main(argv: Optional[list] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not os.environ.get("WP_APP_PASS"):
        print("publish: WP_APP_PASS が未設定のため、投稿をスキップしました。")
        return 0
    rc = selftest()
    if rc != 0 or "--check" in argv:
        return rc
    return publish_tool_page(WordPress())


if __name__ == "__main__":
    raise SystemExit(main())
