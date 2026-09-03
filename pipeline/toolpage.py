"""
診断ツールのページを組み立てる。

これがサイトの中核ページ。記事ではなく道具なので、固定ページとして1枚だけ公開し、
DBが更新されたら同じURLを上書きする。

設計:
  - 正規化（服の実寸 → 犬の適合レンジ）は Python 側で済ませてから配信する。
    ゆとり値の定義が normalize.py とブラウザ側の2箇所に散らばるのを防ぐため。
  - ブラウザ側が持つのは採点だけ（sizing.py と同じ式）。
  - 数値には必ず provenance が付く。付いていない行は配信しない（引継書 第33項）。
  - CSSは .ucs 配下に閉じる。テーマ側と当たらないようにする。
"""

from __future__ import annotations

import html
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Optional

from .article import Article, Source
from .normalize import normalize_ranges

TITLE = "犬服のサイズ診断｜8ブランドの公式サイズ表を横断して調べる"
SLUG = "size-checker"

QUOTE = re.compile(r"原文[:：]\s*[「\"](.+?)[」\"]")


class ToolPageError(RuntimeError):
    pass


def e(s) -> str:
    return html.escape(str(s), quote=True)


# --- データ取り出し ---------------------------------------------------

def export_charts(con: sqlite3.Connection, category: str = "wear") -> list[dict]:
    """表ごとに、正規化済みのサイズ行を返す。"""
    con.row_factory = sqlite3.Row
    charts: dict[tuple, dict] = {}

    for r in con.execute(
            "SELECT * FROM v_size_row WHERE category = ? "
            "ORDER BY brand_name, series, sort_order", (category,)):
        key = (r["brand_slug"], r["series"])
        ch = charts.get(key)
        if ch is None:
            ch = charts[key] = {
                "brand": r["brand_name"],
                "series": r["series"] or "",
                "basis": r["measure_basis"],
                "source_url": r["source_url"],
                "fetched_at": (r["source_fetched_at"] or "")[:10],
                "rows": [],
            }

        raw = {
            "neck": (r["neck_min"], r["neck_max"]),
            "chest": (r["chest_min"], r["chest_max"]),
            "back": (r["back_min"], r["back_max"]),
            "weight": (r["weight_min"], r["weight_max"]),
        }
        n = normalize_ranges(raw, r["measure_basis"], r["stretch"])
        prov = ("estimated" if "estimated" in (r["provenance"], n.provenance)
                else r["provenance"])
        if prov not in ("official", "estimated", "user"):
            raise ToolPageError(f"provenance が不正です: {prov}")

        ch["rows"].append({
            "label": r["size_label"],
            "sort": r["sort_order"],
            "ranges": {d: list(n.ranges.get(d, (None, None))) for d in
                       ("neck", "chest", "back", "weight")},
            "prov": prov,
            "conf": n.confidence,
            "stretch": n.scoring_stretch,
        })

    out = [c for c in charts.values() if c["rows"]]
    if not out:
        raise ToolPageError("サイズ行が1件もありません。DBを確認してください")
    return out


def export_sources(con: sqlite3.Connection) -> list[dict]:
    """公開してよい出典情報だけを取り出す。note からは原文の引用だけを抜く。"""
    con.row_factory = sqlite3.Row
    out = []
    for r in con.execute(
            "SELECT DISTINCT s.url, s.title, s.fetched_at, s.note, b.name AS brand "
            "FROM source s JOIN size_chart c ON c.source_id = s.id "
            "JOIN brand b ON b.id = c.brand_id ORDER BY b.name"):
        m = QUOTE.search(r["note"] or "")
        out.append({"brand": r["brand"], "title": r["title"], "url": r["url"],
                    "fetched_at": (r["fetched_at"] or "")[:10],
                    "quote": m.group(1) if m else ""})
    return out


# --- 画面 -------------------------------------------------------------

CSS = """
.ucs{--ucs-surface:#fff;--ucs-ground:#FBFAF7;--ucs-sunk:#F2F0EA;--ucs-ink:#1A1917;
 --ucs-ink2:#403E39;--ucs-muted:#6E6B63;--ucs-line:#E4E1D9;--ucs-line2:#CDC9BE;
 --ucs-accent:#1F5673;--ucs-accent-ink:#fff;--ucs-accent-soft:#E4EDF2;
 --ucs-ok:#2E7D52;--ucs-ok-soft:#E1EFE7;--ucs-warn:#A9761A;--ucs-warn-soft:#F5EBD8;
 --ucs-bad:#A6392F;--ucs-bad-soft:#F5E3E0;
 --ucs-data:ui-monospace,SFMono-Regular,Menlo,monospace;
 color:var(--ucs-ink);line-height:1.8;max-width:46rem;margin:0 auto}
@media (prefers-color-scheme:dark){.ucs{--ucs-surface:#1D2024;--ucs-ground:#15171A;
 --ucs-sunk:#25292E;--ucs-ink:#EDEBE6;--ucs-ink2:#C8C5BE;--ucs-muted:#8F8D86;
 --ucs-line:#31353B;--ucs-line2:#474C54;--ucs-accent:#7FB6D4;--ucs-accent-ink:#10161A;
 --ucs-accent-soft:#1B2A33;--ucs-ok:#71C295;--ucs-ok-soft:#18271F;--ucs-warn:#D6A44C;
 --ucs-warn-soft:#2B2417;--ucs-bad:#E08B80;--ucs-bad-soft:#2E1D1B}}
.ucs *{box-sizing:border-box}
.ucs .panel{background:var(--ucs-surface);border:1px solid var(--ucs-line);border-radius:6px;
 padding:1.1rem;margin:1.4rem 0}
.ucs .panel h2,.ucs h2.sec{font-size:1.05rem;font-weight:700;margin:0 0 .2rem;line-height:1.5}
.ucs h2.sec{margin:2.2rem 0 .3rem;font-size:1.15rem}
.ucs .sub,.ucs .sec-note{font-size:.82rem;color:var(--ucs-muted);margin:.1rem 0 1rem}
.ucs .fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(8.5rem,1fr));gap:.75rem}
.ucs .field label{display:block;font-size:.75rem;color:var(--ucs-muted);margin-bottom:.25rem}
.ucs .inputline{display:flex;align-items:center;gap:.35rem;border:1px solid var(--ucs-line2);
 border-radius:4px;background:var(--ucs-ground);padding:.4rem .55rem}
.ucs .field input{border:0;background:transparent;color:var(--ucs-ink);width:100%;
 font-family:var(--ucs-data);font-size:1.02rem;font-variant-numeric:tabular-nums}
.ucs .field input:focus{outline:none}
.ucs .field.empty .inputline{border-style:dashed}
.ucs .unit{font-family:var(--ucs-data);font-size:.75rem;color:var(--ucs-muted)}
.ucs .hint{font-size:.75rem;color:var(--ucs-muted);margin:.85rem 0 0;padding-top:.75rem;
 border-top:1px solid var(--ucs-line)}
.ucs .card{background:var(--ucs-surface);border:1px solid var(--ucs-line);border-radius:6px;
 padding:.9rem 1rem;margin-bottom:.6rem}
.ucs .card.top{border-color:var(--ucs-accent);box-shadow:0 0 0 1px var(--ucs-accent)}
.ucs .cardhead{display:flex;align-items:flex-start;gap:.7rem}
.ucs .rank{font-family:var(--ucs-data);font-size:.72rem;color:var(--ucs-muted);flex:none;
 border:1px solid var(--ucs-line2);border-radius:3px;padding:.05rem .35rem;margin-top:.2rem}
.ucs .card.top .rank{background:var(--ucs-accent);color:var(--ucs-accent-ink);border-color:transparent}
.ucs .brand{flex:1;min-width:0}
.ucs .brand .name{font-weight:700;font-size:.98rem;line-height:1.4}
.ucs .brand .series{font-size:.74rem;color:var(--ucs-muted)}
.ucs .sizebox{text-align:right;flex:none}
.ucs .sizebox .label{font-weight:700;font-size:1.3rem;line-height:1.2;font-variant-numeric:tabular-nums}
.ucs .verdict{display:inline-block;font-size:.75rem;font-weight:700;border-radius:3px;
 padding:.05rem .4rem;white-space:nowrap}
.ucs .v-just,.ucs .v-fits{background:var(--ucs-ok-soft);color:var(--ucs-ok)}
.ucs .v-check{background:var(--ucs-warn-soft);color:var(--ucs-warn)}
.ucs .v-unfit{background:var(--ucs-bad-soft);color:var(--ucs-bad)}
.ucs .bar{height:5px;background:var(--ucs-sunk);border-radius:3px;margin:.7rem 0 .55rem;overflow:hidden}
.ucs .bar i{display:block;height:100%;border-radius:3px}
.ucs .reason{font-size:.83rem;color:var(--ucs-ink2);margin:0}
.ucs .dims{display:flex;flex-wrap:wrap;gap:.3rem;margin-top:.6rem}
.ucs .dim{font-family:var(--ucs-data);font-size:.72rem;border:1px solid var(--ucs-line);
 border-radius:3px;padding:.1rem .4rem;color:var(--ucs-ink2);background:var(--ucs-ground);
 font-variant-numeric:tabular-nums}
.ucs .dim b{font-weight:400;color:var(--ucs-muted);font-family:inherit}
.ucs .dim.out{border-color:var(--ucs-bad);color:var(--ucs-bad)}
.ucs .prov{display:inline-block;font-family:var(--ucs-data);font-size:.66rem;
 border-radius:2px;padding:.05rem .35rem}
.ucs .prov-official{background:var(--ucs-accent-soft);color:var(--ucs-accent)}
.ucs .prov-estimated{border:1px dashed var(--ucs-line2);color:var(--ucs-muted)}
.ucs .cardfoot{display:flex;flex-wrap:wrap;gap:.5rem;align-items:center;margin-top:.65rem;
 padding-top:.55rem;border-top:1px solid var(--ucs-line);font-size:.75rem}
.ucs .tablewrap{overflow-x:auto;border:1px solid var(--ucs-line);border-radius:6px;
 background:var(--ucs-surface)}
.ucs table{border-collapse:collapse;width:100%;min-width:32rem;font-size:.82rem;margin:0}
.ucs th,.ucs td{padding:.5rem .6rem;text-align:left;border-bottom:1px solid var(--ucs-line);
 white-space:nowrap}
.ucs thead th{background:var(--ucs-sunk);font-size:.72rem;color:var(--ucs-muted)}
.ucs tbody th{font-weight:500;position:sticky;left:0;background:var(--ucs-surface);
 border-right:1px solid var(--ucs-line)}
.ucs td.num{font-family:var(--ucs-data);font-variant-numeric:tabular-nums}
.ucs .sources{list-style:none;padding:0;margin:0;font-size:.8rem}
.ucs .sources li{padding:.6rem 0;border-bottom:1px solid var(--ucs-line)}
.ucs .sources li:last-child{border-bottom:0}
.ucs .sources .q{color:var(--ucs-muted);display:block;font-size:.76rem;margin-top:.15rem}
.ucs .sources .meta{font-family:var(--ucs-data);font-size:.68rem;color:var(--ucs-muted)}
.ucs .legend{font-size:.78rem;color:var(--ucs-muted);display:flex;gap:.6rem;flex-wrap:wrap;
 margin:.6rem 0 0}
"""

ENGINE = r"""
(function(){
var W={chest:.50,back:.25,neck:.20,weight:.05};
var OVER={chest:3.0,neck:3.0,back:1.6,weight:2.2};
var UNDER={chest:1.4,neck:1.2,back:1.8,weight:.8};
var SLACK={none:0,low:.03,high:.08};
var SWEET=.45;
var JA={neck:"首回り",chest:"胴回り",back:"着丈",weight:"体重"};
var U={neck:"cm",chest:"cm",back:"cm",weight:"kg"};
var V={just:{m:"◎",j:"ぴったり",c:"v-just",col:"var(--ucs-ok)"},
       fits:{m:"○",j:"適合",c:"v-fits",col:"var(--ucs-ok)"},
       check:{m:"△",j:"要確認",c:"v-check",col:"var(--ucs-warn)"},
       unfit:{m:"×",j:"範囲外",c:"v-unfit",col:"var(--ucs-bad)"}};
var DATA=JSON.parse(document.getElementById("ucs-data").textContent);

function span(lo,hi){if(lo!==null&&hi!==null&&hi>lo)return hi-lo;
  var b=hi!==null?hi:lo;return b?Math.max(Math.abs(b)*.10,.5):1.0;}

function scoreDim(d,v,lo,hi,st){
  if(lo===null&&hi===null)return null;
  var sp=span(lo,hi),sl=SLACK[st]||0,ehi=hi!==null?hi*(1+sl):null;
  if(ehi!==null&&v>ehi)return{dim:d,value:v,lo:lo,hi:hi,dir:"over",
    score:Math.exp(-OVER[d]*((v-ehi)/sp)),
    reason:JA[d]+" "+v+U[d]+" は上限 "+hi+U[d]+" を超えています"};
  if(lo!==null&&v<lo)return{dim:d,value:v,lo:lo,hi:hi,dir:"under",
    score:Math.exp(-UNDER[d]*((lo-v)/sp)),
    reason:JA[d]+" "+v+U[d]+" は下限 "+lo+U[d]+" を下回ります"};
  var s,r;
  if(lo!==null&&hi!==null&&hi>lo){
    var sw=lo+(hi-lo)*SWEET,off=Math.abs(v-sw)/(hi-lo);
    s=1.0-Math.min(off,1.0)*.30;
    r=JA[d]+(v>sw?" は範囲内（やや詰まり気味）":" は範囲内（余裕あり）");
  }else{s=.95;r=JA[d]+" は範囲内";}
  return{dim:d,value:v,lo:lo,hi:hi,dir:"in",score:s,reason:r};
}

function evaluate(dog,row,chart){
  var dims=[],acc=0,tw=0;
  for(var d in W){var v=dog[d];
    if(v===null||v===undefined||isNaN(v))continue;
    var rg=row.ranges[d]||[null,null];
    var r=scoreDim(d,v,rg[0],rg[1],row.stretch);
    if(!r)continue;dims.push(r);acc+=r.score*W[d];tw+=W[d];}
  if(tw===0)return null;
  var sc=acc/tw;
  for(var i=0;i<dims.length;i++)
    if(dims[i].dim==="chest"&&dims[i].dir!=="in"&&dims[i].score<.5)sc=Math.min(sc,.45);
  var low=!dims.some(function(x){return x.dim==="chest";});
  if(low)sc=Math.min(sc,.89);
  var vd=sc>=.90?"just":sc>=.75?"fits":sc>=.55?"check":"unfit";
  return{row:row,chart:chart,score:sc,verdict:vd,dims:dims,low:low};
}

function best(dog,chart){
  var f=chart.rows.map(function(r){return evaluate(dog,r,chart);})
                  .filter(function(x){return x;});
  if(!f.length)return null;
  f.sort(function(a,b){return (b.score-a.score)||(a.row.sort-b.row.sort);});
  return f[0];
}

function esc(s){return String(s).replace(/[&<>"]/g,function(c){
  return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];});}
function rng(r){
  if(r[0]===null&&r[1]===null)return"—";
  if(r[0]===null)return"〜"+r[1];
  if(r[1]===null)return r[0]+"〜";
  return r[0]===r[1]?String(r[0]):r[0]+"〜"+r[1];}

function readDog(){
  function n(id){var el=document.getElementById(id);
    var v=el.value.trim();return v===""?null:parseFloat(v);}
  return{weight:n("ucs-weight"),chest:n("ucs-chest"),neck:n("ucs-neck"),back:n("ucs-back")};}

function render(){
  var dog=readDog();
  Array.prototype.forEach.call(document.querySelectorAll(".ucs .field"),function(f){
    var i=f.querySelector("input");
    if(i.value.trim()===""){f.className="field empty";}else{f.className="field";}});

  var fits=DATA.charts.map(function(c){return best(dog,c);})
    .filter(function(x){return x;})
    .sort(function(a,b){return (b.score-a.score)||
      a.chart.brand.localeCompare(b.chart.brand,"ja");});

  var box=document.getElementById("ucs-results");
  var cmp=document.getElementById("ucs-cmp");
  var cnt=document.getElementById("ucs-count");
  if(!fits.length){
    box.innerHTML='<div class="card"><p class="reason">寸法が1つも入力されていません。</p></div>';
    cmp.innerHTML="";cnt.textContent="";return;}
  cnt.textContent=fits.length+"ブランド";

  box.innerHTML=fits.map(function(f,i){
    var v=V[f.verdict];
    var out=f.dims.filter(function(d){return d.dir!=="in";})
                  .sort(function(a,b){return a.score-b.score;})[0];
    var reason;
    if(out){reason=out.reason+(f.verdict==="check"?"ので、購入前にご確認ください。":"。");}
    else{var t=f.dims.filter(function(d){return d.dir==="in"&&d.score<.85;})[0];
      reason=t?t.reason+"。":"入力したすべての寸法が、このブランドの公式サイズ表の適合範囲に入っています。";}
    if(f.low)reason+=" 胴回りの実測がないため、判定は「適合」までにとどめています。";
    if(f.row.prov==="estimated")
      reason+=" このブランドの公式表は服の実寸表記のため、犬の寸法へ換算した推定値で判定しています。";
    var dims=f.dims.map(function(d){
      return '<span class="dim'+(d.dir==="in"?"":" out")+'"><b>'+JA[d.dim]+'</b> '+
        d.value+U[d.dim]+' / '+rng([d.lo,d.hi])+'</span>';}).join("");
    var prov=f.row.prov==="official"
      ? '<span class="prov prov-official" data-prov="official">公式値</span>'
      : '<span class="prov prov-estimated" data-prov="estimated">推定値 '+f.row.conf+'</span>';
    return '<article class="card'+(i===0?" top":"")+'">'+
      '<div class="cardhead"><span class="rank">'+(i+1)+'</span>'+
      '<div class="brand"><div class="name">'+esc(f.chart.brand)+'</div>'+
      '<div class="series">'+esc(f.chart.series)+'</div></div>'+
      '<div class="sizebox"><div class="label">'+esc(f.row.label)+'</div>'+
      '<span class="verdict '+v.c+'">'+v.m+' '+v.j+'</span></div></div>'+
      '<div class="bar"><i style="width:'+Math.round(f.score*100)+
      '%;background:'+v.col+'"></i></div>'+
      '<p class="reason">'+esc(reason)+'</p>'+
      '<div class="dims">'+dims+'</div>'+
      '<div class="cardfoot">'+prov+
      '<a href="'+esc(f.chart.source_url)+'" target="_blank" rel="nofollow noopener">公式サイズ表を見る</a>'+
      '<span class="prov prov-estimated">取得 '+esc(f.chart.fetched_at)+'</span></div></article>';
  }).join("");

  cmp.innerHTML=fits.map(function(f){
    var v=V[f.verdict];
    return '<tr><th>'+esc(f.chart.brand)+'</th><td><strong>'+esc(f.row.label)+
      '</strong></td><td class="num">'+rng(f.row.ranges.chest)+' cm</td>'+
      '<td style="color:'+v.col+'">'+v.m+' '+v.j+'</td><td>'+
      (f.row.prov==="official"?"公式値":"換算した推定値")+'</td></tr>';}).join("");
}

Array.prototype.forEach.call(document.querySelectorAll(".ucs .fields input"),
  function(i){i.addEventListener("input",render);});
render();
})();
"""


def _payload(charts: list[dict]) -> dict:
    """ブラウザへ渡すのは採点に要る分だけ。社内の判断用フィールドは載せない。"""
    return {"charts": [{
        "brand": c["brand"], "series": c["series"],
        "source_url": c["source_url"], "fetched_at": c["fetched_at"],
        "rows": [{"label": r["label"], "sort": r["sort"], "ranges": r["ranges"],
                  "prov": r["prov"], "conf": r["conf"], "stretch": r["stretch"]}
                 for r in c["rows"]],
    } for c in charts]}


def render_page(charts: list[dict], sources: list[dict]) -> str:
    data = json.dumps(_payload(charts), ensure_ascii=False, separators=(",", ":"))
    n_brand = len({c["brand"] for c in charts})
    n_row = sum(len(c["rows"]) for c in charts)

    src_li = "\n".join(
        f'<li><a href="{e(s["url"])}" target="_blank" rel="nofollow noopener">'
        f'{e(s["brand"])}「{e(s["title"])}」</a>'
        + (f'<span class="q">原文：{e(s["quote"])}</span>' if s["quote"] else "")
        + f'<span class="meta">取得 {e(s["fetched_at"])}</span></li>'
        for s in sources)

    return f"""<div class="ucs">
<style>{CSS}</style>

<p>うちの子の実測値を入れると、{n_brand}ブランドの公式サイズ表を横断して、
それぞれどのサイズの適合範囲に入るかを表示します。
掲載している{n_row}行はすべて各ブランドの公式サイズ表の値で、出典と取得日を併記しています。</p>

<section class="panel">
  <h2>うちの子の寸法を入れる</h2>
  <p class="sub">分かる項目だけで動きます。胴回りが最も重要です。</p>
  <div class="fields">
    <div class="field"><label for="ucs-weight">体重</label>
      <div class="inputline"><input id="ucs-weight" type="number" step="0.1" value="3.2" inputmode="decimal"><span class="unit">kg</span></div></div>
    <div class="field"><label for="ucs-chest">胴回り</label>
      <div class="inputline"><input id="ucs-chest" type="number" step="0.5" value="38" inputmode="decimal"><span class="unit">cm</span></div></div>
    <div class="field"><label for="ucs-neck">首回り</label>
      <div class="inputline"><input id="ucs-neck" type="number" step="0.5" value="25" inputmode="decimal"><span class="unit">cm</span></div></div>
    <div class="field"><label for="ucs-back">着丈</label>
      <div class="inputline"><input id="ucs-back" type="number" step="0.5" value="26" inputmode="decimal"><span class="unit">cm</span></div></div>
  </div>
  <p class="hint">胴回りを空欄にすると、判定は「◎ ぴったり」を出しません。
  体重だけの判定は、胴の長い犬や毛量の多い犬で外れるためです。</p>
</section>

<h2 class="sec">ブランド別の推奨サイズ <span id="ucs-count"></span></h2>
<p class="sec-note">各ブランドの公式サイズ表のうち、入力値が最もよく収まる1サイズを表示しています。
順位は適合度の高い順です。実際の着用感は個体差があるため、購入前に各ブランドの表もご確認ください。</p>
<div id="ucs-results"></div>
<p class="legend"><span class="prov prov-official" data-prov="official">公式値</span>
ブランドが公開している数値をそのまま使っています
<span class="prov prov-estimated" data-prov="estimated">推定値</span>
公式表が服の実寸表記のため、犬の寸法へ換算しています</p>

<h2 class="sec">横断比較</h2>
<p class="sec-note">同じ体でも、ブランドによってサイズ名も適合範囲も違います。
「S を買ったのに入らなかった」はこれが原因です。</p>
<div class="tablewrap"><table>
<thead><tr><th>ブランド</th><th>推奨サイズ</th><th>胴回りの適合範囲</th><th>判定</th><th>数値の出所</th></tr></thead>
<tbody id="ucs-cmp"></tbody></table></div>

<h2 class="sec">出典</h2>
<p class="sec-note">サイズ表が「犬の実測」を指すのか「服の仕上がり寸法」を指すのかは、
各ブランドの公式ページの記載を引用して判定しています。記載がないブランドは掲載していません。</p>
<ul class="sources">
{src_li}
</ul>

<script type="application/json" id="ucs-data">{data}</script>
<script>{ENGINE}</script>
</div>"""


def build_tool_page(db_path: Optional[Path] = None) -> Article:
    from .build_db import DEFAULT_OUT, build
    path = Path(db_path) if db_path else DEFAULT_OUT
    if not path.exists():
        build(path)

    con = sqlite3.connect(str(path))
    try:
        charts = export_charts(con)
        sources = export_sources(con)
    finally:
        con.close()

    if not sources:
        raise ToolPageError("出典が1件もありません。出典なしのページは公開しません")

    return Article(
        title=TITLE,
        slug=SLUG,
        body=render_page(charts, sources),
        sources=[Source(brand=s["brand"], url=s["url"], fetched_at=s["fetched_at"])
                 for s in sources],
    )


def main(argv: list[str]) -> int:
    out = Path(argv[0]) if argv else Path("build/tool.html")
    try:
        art = build_tool_page()
    except ToolPageError as exc:
        print(f"NG: {exc}", file=sys.stderr)
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(art.body, encoding="utf-8")
    print(f"toolpage: {out} を書き出しました（{len(art.body)}文字 / 出典{len(art.sources)}件）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
