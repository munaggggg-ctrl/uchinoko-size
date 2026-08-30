"""楽天APIが何を求めているのかを一度で確定させる使い捨ての診断。
原因が分かったら削除する。"""
import json, os, urllib.error, urllib.parse, urllib.request

BASE = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701"
Q = {
    "applicationId": os.environ["RAKUTEN_APP_ID"],
    "accessKey": os.environ["RAKUTEN_ACCESS_KEY"],
    "affiliateId": os.environ.get("RAKUTEN_AFFILIATE_ID", ""),
    "keyword": "犬服", "hits": "1", "format": "json", "formatVersion": "2",
}
URL = BASE + "?" + urllib.parse.urlencode(Q)

CASES = [
    ("ヘッダなし",                       {}),
    ("Referer 末尾スラッシュあり",        {"Referer": "https://uchinoko-size.com/"}),
    ("Referer 末尾スラッシュなし",        {"Referer": "https://uchinoko-size.com"}),
    ("Referer + Origin",                {"Referer": "https://uchinoko-size.com/",
                                         "Origin": "https://uchinoko-size.com"}),
    ("Referer + ブラウザ風UA",           {"Referer": "https://uchinoko-size.com/",
                                         "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                                                       "Chrome/140.0.0.0 Safari/537.36"}),
    ("Referer 記事URL風",                {"Referer": "https://uchinoko-size.com/size/chihuahua/"}),
]

for name, extra in CASES:
    headers = {"User-Agent": "uchinoko-size/1.0"}
    headers.update(extra)
    try:
        with urllib.request.urlopen(
                urllib.request.Request(URL, headers=headers), timeout=20) as r:
            body = r.read().decode("utf-8")
            n = json.loads(body).get("count", "?")
            print(f"  OK   {name:<28} status={r.status} count={n}")
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", "replace").replace("\n", " ")
        print(f"  NG   {name:<28} status={e.code} {msg[:120]}")
    except Exception as e:
        print(f"  NG   {name:<28} {type(e).__name__}: {e}")
