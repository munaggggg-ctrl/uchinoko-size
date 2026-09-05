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


TOOL_URL = "/size-checker/"


def weight_article(weight: float,
                   fits: Sequence[tuple[Fit, Source]],
                   offers: Sequence[Offer] = (),
                   excluded_brands: Sequence[str] = ()) -> Article:
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

    # 測った数値を入れれば、この記事より正確な判定になる。
    # 記事は入口で、道具が出口。この導線を切らない。
    p.append(
        f'<p>測り終えたら、<a href="{TOOL_URL}">サイズ診断</a>に'
        f'その数値を入れてください。体重だけの比較より判定が絞り込まれます。</p>')

    if excluded_brands:
        names = "・".join(excluded_brands)
        p.append(
            f'<p class="note">{e(names)} は対応体重を公開していないため、'
            f'上の表には出ていません。胴回りを測れば'
            f'<a href="{TOOL_URL}">サイズ診断</a>で比較できます。</p>')

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


# =====================================================================
# 採寸ガイド
#
# なぜこの記事を最初の柱にするか:
#   飼い主が知っているのは体重だけで、胴回りを測ったことがある人は少ない。
#   つまり全ての導線の手前に「測る」という段差がある。ここを取らないと、
#   サイズ比較のページに来ても入力できずに離脱する。
#
# 薄い記事にしないために:
#   採寸方法の説明そのものは、どのブランドのサイトにも書いてある。
#   当サイトが足せるのは「ブランドによって、その数字の意味が違う」という
#   横断調査の結果である。これは1社だけを見ていては書けない。
#   その調査結果を本文に含めることを、この関数の必須条件とする。
# =====================================================================

@dataclass
class BasisSurvey:
    """サイズ表の基準を、実際に調べた結果。推測ではなく調査した数のみを入れる。"""
    dog_fit_brands: list[str]      # 犬の体のサイズで表記しているブランド
    garment_brands: list[str]      # 服の実寸で表記しているブランド
    unknown_brands: list[str]      # 公式に明記がなく、判定できなかったブランド

    @property
    def total(self) -> int:
        return len(self.dog_fit_brands) + len(self.garment_brands) + len(self.unknown_brands)


def measuring_guide_article(survey: BasisSurvey,
                            sources: Sequence[Source],
                            quotes: Sequence[tuple[str, str]] = ()) -> Article:
    """「犬の採寸ガイド」記事。

    quotes は (ブランド名, 公式ページの原文) の組。基準の違いを示す根拠として載せる。
    調査結果が無い状態では、他所と同じ薄い記事になってしまうので、
    survey が空なら組み立てを拒否する。
    """
    if survey.total == 0:
        raise ValueError(
            "横断調査の結果がないまま採寸ガイドを組み立てない。"
            "採寸方法の説明だけでは、どこにでもある記事にしかならない。")

    title = "犬の首回り・胴回り・着丈の測り方｜ブランドで意味が違う点に注意"
    slug = "how-to-measure-dog"
    p: list[str] = []

    p.append(
        f"<p>犬服やハーネスのサイズ選びで失敗する原因の多くは、"
        f"体重だけで選んでしまうことにあります。ここでは首回り・胴回り・着丈の測り方と、"
        f"<strong>測った数字をブランドのサイズ表とどう照らし合わせるか</strong>を説明します。</p>")

    # --- 測り方 ---
    p.append("<h2>測る前に用意するもの</h2>")
    p.append(
        "<p>やわらかいメジャー（洋裁用のもの）を使います。金属の巻尺だと体に沿わず、"
        "数cm変わります。手元にない場合は、ひもを体に回して印を付け、"
        "あとから定規で測っても構いません。</p>"
        "<p>犬が立っている状態で測ります。座らせると胴回りが変わります。</p>")

    p.append("<h2>3か所の測り方</h2>")
    p.append(
        "<h3>1. 首回り</h3>"
        "<p>首輪をつける位置を、ひと回りします。喉の下のいちばん細い部分ではなく、"
        "首の付け根寄りです。</p>"
        "<h3>2. 胴回り</h3>"
        "<p>前足の付け根のすぐ後ろを通して、胴のいちばん太いところをひと回りします。"
        "<strong>3か所のうち、サイズ選びをいちばん左右するのがここです。</strong></p>"
        "<h3>3. 着丈（背丈）</h3>"
        "<p>首の付け根から、しっぽの付け根までの長さです。首輪の位置から測り始めます。</p>"
        "<p>いずれも、指が1本入る程度のゆとりを持たせて当ててください。"
        "きつく締めて測ると、実際より小さい数字になります。</p>")

    # --- ここが独自部分 ---
    p.append("<h2>測った数字を、そのまま比べてはいけない</h2>")
    p.append(
        f"<p>当サイトで小型犬向けブランド{survey.total}社の公式サイズ表を調べたところ、"
        f"<strong>サイズ表の数字が何を指しているかがブランドによって違いました。</strong></p>")

    p.append('<div class="tw"><table>')
    p.append("<thead><tr><th>サイズ表の数字が指すもの</th><th>社数</th><th>ブランド</th></tr></thead><tbody>")
    rows = [("犬の体のサイズ", survey.dog_fit_brands),
            ("服そのものの寸法（実寸）", survey.garment_brands),
            ("公式に明記なし", survey.unknown_brands)]
    for label, brands in rows:
        if not brands:
            continue
        p.append(f"<tr><th>{e(label)}</th><td>{len(brands)}社</td>"
                 f"<td>{e('、'.join(brands))}</td></tr>")
    p.append("</tbody></table></div>")

    if quotes:
        p.append("<p>各社の公式ページには、次のように書かれています。</p><ul>")
        for brand, quote in quotes:
            p.append(f"<li><strong>{e(brand)}</strong>：「{e(quote)}」</li>")
        p.append("</ul>")

    p.append(
        "<p><strong>この違いを知らないと、同じ数字を見ているのに逆の結論になります。</strong>"
        "「服の実寸」で書かれた表に、測った胴回りをそのまま当てはめると、"
        "ゆとりがゼロの服を選ぶことになり、着られません。</p>"
        "<p>「服の実寸」表記のブランドでは、測った数字より数cm大きいサイズを選ぶ必要があります。"
        "犬服の型紙販売元 milla milla が公開している推奨あき量では、小型犬の場合、"
        '<span data-prov="official">ニット生地で胴回り2〜3cm・首回り2cm、'
        '伸びない生地で胴回り4〜5cm・首回り2〜3cm</span>とされています。</p>')

    p.append("<h2>測ったあとにすること</h2>")
    p.append(
        "<p>3か所の数字が出たら、メモに残しておいてください。"
        "買い物のたびに測り直す必要はありません（成長期の子犬を除く）。</p>"
        "<p>当サイトのサイズ比較では、この3つの数字を入れると、"
        "ブランドごとの推奨サイズを表記の違いを補正したうえで並べて表示します。</p>")

    # --- 出典 ---
    p.append("<h2>出典</h2><ul>")
    seen, srcs = set(), []
    for s_ in sources:
        if s_.url not in seen:
            seen.add(s_.url); srcs.append(s_)
    for s_ in srcs:
        p.append(f'<li>{e(s_.brand)}：<a href="{e(s_.url)}" rel="nofollow noopener" '
                 f'target="_blank">公式サイズ表</a>（{e(s_.fetched_at)} 取得）</li>')
    p.append('<li>milla milla：<a href="https://www.millamilla.jp/first/'
             '%E3%82%B5%E3%82%A4%E3%82%BA%E3%81%AB%E3%81%A4%E3%81%84%E3%81%A6/" '
             'rel="nofollow noopener" target="_blank">サイズについて【犬用】</a>（2026-08-29 取得）</li>')
    p.append("</ul>")

    return Article(title=title, slug=slug, body="\n".join(p), sources=srcs)
