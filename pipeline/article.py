"""
記事の組み立て。

方針:
  記事の中心は文章ではなく「他のどこにも載っていない表」である（引継書 第31項）。
  文章はその表を読むための補助に過ぎない。だからテンプレートで組み、LLMは使わない。
  LLMを使わないので、生成コストはゼロ、出力は毎回同じ、テストで固定できる。

なぜ体重を軸にするか:
  飼い主が確実に知っているのは体重だけで、胴回りを知っている人は少ない。
  そして「対応体重」は各ブランドが公式に公開している値なので、出典を示せる。
  犬種別の平均採寸値は公式な出典を用意できていないため、v1では扱わない
  （推測値を載せない、という原則を記事側でも守る）。

出力は必ず pipeline.lint を通す前提で組み立てる:
  - 数値には data-prov を付ける（公式値か推定値かを明示）
  - 出典リンクと取得日を必ず入れる
  - アフィリエイトリンクを入れる場合は広告表記を本文の先頭に置く
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from typing import Optional, Sequence

from .sizing import CHECK, FITS, JUST, UNFIT, Dog, Fit

VERDICT_JA = {JUST: "ぴったり", FITS: "適合", CHECK: "要確認", UNFIT: "合わない"}
AD_DISCLOSURE = "本記事は広告を含みます。"


@dataclass
class Source:
    brand: str
    url: str
    fetched_at: str


@dataclass
class Offer:
    """商品の購入導線。楽天APIから取得したアフィリエイトリンクを入れる。"""
    name: str
    price: int
    url: str
    merchant: str = "楽天市場"


@dataclass
class Article:
    title: str
    slug: str
    body: str
    sources: list[Source] = field(default_factory=list)

    @property
    def has_offers(self) -> bool:
        return "hb.afl.rakuten.co.jp" in self.body


def e(s) -> str:
    return html.escape(str(s), quote=True)


def _range(lo: Optional[float], hi: Optional[float], unit: str) -> str:
    if lo is None and hi is None:
        return "—"
    if lo is None:
        return f"〜{hi}{unit}"
    if hi is None or lo == hi:
        return f"{lo}{unit}"
    return f"{lo}〜{hi}{unit}"


def _mark(fit: Fit) -> str:
    return f'<span class="mark">{fit.mark}</span>'


def weight_article(weight: float,
                   fits: Sequence[tuple[Fit, Source]],
                   offers: Sequence[Offer] = ()) -> Article:
    """「体重◯kgの小型犬に合う犬服サイズ」記事を組み立てる。

    fits は (適合判定, 出典) の組。適合度の高い順に並んでいることを前提とする。
    """
    w = f"{weight:g}"
    title = f"体重{w}kgの小型犬に合う犬服のサイズ｜{len(fits)}ブランド横断比較"
    slug = f"dog-wear-size-{w.replace('.', '-')}kg"

    p: list[str] = []

    if offers:
        p.append(f"<p>{AD_DISCLOSURE}</p>")

    p.append(
        f"<p>体重{w}kgの小型犬に合う犬服のサイズを、{len(fits)}ブランドのサイズ表を"
        f"横断して比較しました。<strong>同じ体重でもブランドによって推奨サイズは違います。</strong>"
        f"数値はすべて各ブランド公式サイトの公開サイズ表によるものです。</p>")

    # --- 結論の表。これが記事の中心 ---
    p.append("<h2>ブランド別の推奨サイズ</h2>")
    p.append('<div class="tw"><table>')
    p.append("<thead><tr><th>ブランド</th><th>推奨サイズ</th><th>適合</th>"
             "<th>首回り</th><th>胴回り</th><th>着丈</th><th>対応体重</th></tr></thead><tbody>")
    for fit, src in fits:
        v = fit.variant
        prov = "official" if fit.provenance == "official" else "estimated"
        cells = []
        for dim, unit in (("neck", "cm"), ("chest", "cm"), ("back", "cm"), ("weight", "kg")):
            lo, hi = v.range_of(dim)
            cells.append(f'<td data-prov="{prov}">{_range(lo, hi, unit)}</td>')
        p.append(
            f"<tr><th>{e(v.brand_name)}</th>"
            f"<td><strong>{e(v.size_label)}</strong></td>"
            f"<td>{_mark(fit)} {VERDICT_JA[fit.verdict]}</td>"
            + "".join(cells) + "</tr>")
    p.append("</tbody></table></div>")

    if fits and all(f.low_coverage for f, _ in fits):
        p.append(
            '<p class="note">この表は<strong>体重だけを手がかりにした比較</strong>です。'
            'ブランドが公開している対応体重と照らしただけなので、'
            '胴が長い犬種や毛量の多い犬では外れます。'
            'このあとの採寸を済ませてから、もう一度お確かめください。</p>')

    est = [f for f, _ in fits if f.provenance == "estimated"]
    if est:
        names = "・".join(sorted({f.variant.brand_name for f in est}))
        p.append(
            f'<p class="note">{e(names)} のサイズ表は「服そのものの寸法」で公開されているため、'
            f'当サイトでゆとり量を引いて体のサイズに換算しています。'
            f'この行の数値は<strong>当サイトの推定値</strong>で、公式値ではありません。</p>')

    # --- なぜ分かれるのか ---
    p.append("<h2>同じ体重でもサイズが分かれる理由</h2>")
    p.append(
        "<p>体重が同じでも、体型は犬ごとに違います。"
        "胴が長い子は着丈が足りなくなり、首が太い子は首回りで引っかかります。"
        "さらにブランドによって、サイズ表の数値が「犬の体のサイズ」を指す場合と"
        "「服そのものの寸法」を指す場合があり、同じ数字を見ても意味が違います。</p>")

    reasons = [(f, s) for f, s in fits if f.limiting]
    if reasons:
        p.append("<h3>判定が下がった理由</h3><ul>")
        for fit, _ in reasons:
            p.append(f"<li><strong>{e(fit.variant.brand_name)} {e(fit.variant.size_label)}</strong>："
                     f"{e(fit.limiting.reason)}</li>")
        p.append("</ul>")

    # --- 採寸の案内。ここが全導線の入口になる ---
    p.append("<h2>正確に選ぶには実測が要ります</h2>")
    p.append(
        "<p>体重だけで選ぶと、胴長の犬種や毛量の多い犬では外れます。"
        "次の3か所を測ると、この表の数値と直接照らし合わせられます。</p>"
        "<ol>"
        "<li><strong>首回り</strong>：首輪をつける位置をひと回り</li>"
        "<li><strong>胴回り</strong>：前足の付け根を通る、いちばん太いところ</li>"
        "<li><strong>着丈</strong>：首の付け根からしっぽの付け根まで</li>"
        "</ol>"
        "<p>メジャーは指が1本入る程度のゆとりを持たせて当ててください。</p>")

    # --- 購入導線 ---
    if offers:
        p.append("<h2>この体重帯で選ばれている商品</h2>")
        p.append("<ul>")
        for o in offers:
            p.append(f'<li><a href="{e(o.url)}" rel="nofollow noopener" target="_blank">'
                     f'{e(o.name)}</a>（{o.price:,}円 / {e(o.merchant)}）</li>')
        p.append("</ul>")

    # --- 出典 ---
    srcs: list[Source] = []
    seen = set()
    for _, s in fits:
        if s.url not in seen:
            seen.add(s.url)
            srcs.append(s)
    p.append("<h2>出典</h2><ul>")
    for s in srcs:
        p.append(f'<li>{e(s.brand)}：<a href="{e(s.url)}" rel="nofollow noopener" '
                 f'target="_blank">公式サイズ表</a>（{e(s.fetched_at)} 取得）</li>')
    p.append("</ul>")
    p.append("<p>実際の商品は素材やデザインでサイズが変わります。"
             "購入前に各商品ページのサイズ表をご確認ください。</p>")

    return Article(title=title, slug=slug, body="\n".join(p), sources=srcs)
