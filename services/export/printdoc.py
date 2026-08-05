"""인쇄용 문서 — 문항 인쇄본 · 슬라이드 대본 인쇄본.

왜 필요한가
────────────────────────────────────────────────────────────────────────────
화면 검수는 한 문항씩 본다. 그런데 **회차 전체를 훑어야 잡히는 오류**가 따로 있다 —
같은 개념이 두 번 나오는 것, 정답 분포가 한쪽으로 쏠린 것, 난이도가 앞뒤로 튀는 것.
그건 종이로 봐야 보인다. 그리고 다른 사람에게 검수를 부탁할 때 앱을 띄우게 할 수는 없다.

왜 파일을 만들지 않는가
────────────────────────────────────────────────────────────────────────────
`06/` 처럼 산출물을 굽지 않고 **요청할 때마다 지금 데이터로 그린다.**
파일로 두면 고친 뒤 다시 굽는 것을 잊고, 낡은 종이를 들고 검수하게 된다.
이 프로젝트에서 이미 그 사고를 겪었다(업로드 폴더가 옛 빌드였던 일).
브라우저에서 Ctrl+P 로 PDF 를 만드는 것이 인쇄 경로다 — 별도 라이브러리가 없다.

무엇을 어디서 읽는가
────────────────────────────────────────────────────────────────────────────
  문항        `06/pd/<pd>/problems.json`   빌드 산출물. 서버에 올린 것과 **같은 것**이다.
                                           02/*.md 를 다시 파싱하지 않는 이유가 이것이다 —
                                           종이와 서버가 갈리면 검수가 무의미해진다.
  그림        `06/pd/<pd>/figs/*.svg`      `/book` 마운트로 그대로 띄운다.
  슬라이드·대본 `05/<번들>/script/<번들>_script.json`
                                           씬마다 heading(화면에 나오는 제목)과
                                           narration(읽는 말)이 짝으로 있다. 이 둘을
                                           나란히 두는 것이 '슬라이드 최종텍스트' 다.

★ 수식은 로컬 MathJax(`static/vendor/tex-svg.js`)로 그린다. 인터넷 없이 인쇄된다.
"""

from __future__ import annotations

import html
import json
import os
import re

from services.book import paths

# ─────────────────────────────────────────────────────────────────────────────
# 공통
# ─────────────────────────────────────────────────────────────────────────────

_CIRCLE = "①②③④⑤⑥⑦⑧⑨⑩"


def _h(s) -> str:
    return html.escape("" if s is None else str(s))


def _load_problems() -> list[dict]:
    """`06/pd/<pd>/problems.json` 의 문항 목록.

    ★ 여기서 실패하면 빈 목록이 아니라 **예외**를 낸다. 인쇄물이 조용히 0문항으로
      나오면 사람이 "아직 안 만들었나" 로 읽고 원인을 찾지 못한다.
    """
    p = paths.problems_json()
    if not os.path.isfile(p):
        raise FileNotFoundError(
            f"problems.json 이 없습니다: {p}\n"
            "발행 화면 ③ [빌드 실행] 을 먼저 하십시오 — 인쇄본은 빌드 산출물을 읽습니다."
        )
    d = json.load(open(p, encoding="utf-8"))
    if isinstance(d, dict):
        d = d.get("problems") or []
    if not isinstance(d, list):
        raise ValueError(f"problems.json 형식을 알 수 없습니다: {p}")
    return d


def _fig_url(name: str) -> str:
    """그림 URL. `/book` 은 BOOK 폴더 루트를 가리킨다(app.py 의 마운트)."""
    from core.constants import PD_CODE
    return "/book/06/pd/" + PD_CODE + "/figs/" + name


# ─────────────────────────────────────────────────────────────────────────────
# 인쇄 CSS — 두 문서가 같은 것을 쓴다
# ─────────────────────────────────────────────────────────────────────────────

_CSS = """
:root{--ink:#151812;--mute:#666;--line:#d8dcd4;--box:#f6f7f4;--ok:#0f7355;--hi:#8a4b00}
*{box-sizing:border-box}
body{margin:0;padding:22px 26px 40px;color:var(--ink);background:#fff;
  font:13.5px/1.72 -apple-system,"Malgun Gothic","맑은 고딕",sans-serif}
h1{font-size:20px;margin:0 0 3px}
.sub{color:var(--mute);font-size:12.5px;margin:0 0 18px}
.toolbar{position:sticky;top:0;background:#fff;border-bottom:1px solid var(--line);
  padding:9px 0 11px;margin:0 0 18px;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.toolbar a,.toolbar button{padding:5px 11px;border:1px solid var(--line);border-radius:5px;
  background:#fff;color:var(--ink);text-decoration:none;font:inherit;font-size:12.5px;cursor:pointer}
.toolbar a.on{background:var(--ink);border-color:var(--ink);color:#fff;font-weight:700}
.toolbar .sp{margin-left:auto;color:var(--mute);font-size:12px}

/* 회차·번들 표제 — 새 장으로 시작한다 */
.part{page-break-before:always;break-before:page;border-top:2px solid var(--ink);
  margin:26px 0 14px;padding-top:9px}
.part:first-of-type{page-break-before:auto;break-before:auto;margin-top:0}
.part h2{font-size:16px;margin:0}
.part .m{color:var(--mute);font-size:12px}

/* ★ 한 문항이 페이지에 걸쳐 잘리면 종이 검수가 안 된다 */
.q{page-break-inside:avoid;break-inside:avoid;margin:0 0 15px;padding:0 0 13px;
  border-bottom:1px solid var(--line)}
.q:last-child{border-bottom:0}
.qh{display:flex;gap:8px;align-items:baseline;margin:0 0 5px;flex-wrap:wrap}
.qh .no{font-weight:800;font-size:14.5px}
.qh .tag{font-size:11px;color:var(--mute);border:1px solid var(--line);
  border-radius:3px;padding:0 5px;white-space:nowrap}
.qh .tag.d{border-color:var(--hi);color:var(--hi)}
.qh .key{font:11.5px/1.6 ui-monospace,Consolas,monospace;color:var(--mute)}
.psg{background:var(--box);border:1px solid var(--line);border-radius:5px;
  padding:8px 10px;margin:0 0 7px;white-space:pre-wrap}
.qt{margin:0 0 7px}
pre.sql{background:var(--box);border:1px solid var(--line);border-radius:5px;
  padding:8px 10px;margin:0 0 7px;font:12px/1.6 ui-monospace,Consolas,monospace;
  white-space:pre-wrap}
table.tb{border-collapse:collapse;margin:0 0 7px;font-size:12.5px}
table.tb th,table.tb td{border:1px solid var(--line);padding:4px 8px}
table.tb th{background:var(--box)}
.fig{margin:0 0 7px}
.fig img{max-width:76%;max-height:210px}
ol.ch{margin:0 0 7px;padding:0;list-style:none}
ol.ch li{margin:0 0 2px;padding-left:20px;position:relative}
ol.ch li .c{position:absolute;left:0;font-weight:700}
ol.ch li.a{font-weight:700}
ol.ch li.a::after{content:"  ← 정답";color:var(--ok);font-size:11.5px;font-weight:700}
.ex{background:#f2f7f4;border-left:3px solid var(--ok);border-radius:0 5px 5px 0;
  padding:7px 10px;margin:5px 0 0;white-space:pre-wrap;font-size:13px}
.ex b{color:var(--ok)}

/* 슬라이드 대본
   ★ 열 비율의 근거: 화면(heading)은 '3번 문제' 처럼 짧고 읽는 말(narration)은 길다.
     1:1.25 로 두면 heading 쪽에 빈 공간이 남아 그만큼 페이지가 늘어난다 → .38:1.62.
     번호 열은 두 자리면 충분하다(22px → 18px). 열 간격도 9px → 6px.

   ★ 행 높이(padding:7px)는 **줄이지 않는다.** 검수자가 적색펜으로 ㄱ·ㄴ·ㄷ 같은 표시를
     손으로 적어 온다 — 줄 사이에 쓸 자리가 없으면 종이 검수 자체가 안 된다.
     페이지를 줄이는 것은 열 폭과 빈 줄 접기로 한다(가로는 남고 세로는 필요하다). */
.sc{page-break-inside:avoid;break-inside:avoid;display:grid;
  grid-template-columns:18px minmax(70px,.38fr) 1.62fr;gap:6px;padding:7px 0;
  border-bottom:1px solid var(--line);align-items:start}
.sc .n{color:var(--mute);font-size:11px;text-align:right;padding-top:2px}
.sc .hd{font-weight:700}
.sc .hd .k{display:block;color:var(--mute);font-size:10.5px;font-weight:400}
.sc .nr{white-space:pre-wrap}
.sc.nocap{background:#fbfbf8}
.sc.nocap .hd::after{content:" (캡처 안 함)";color:var(--mute);font-size:10.5px;font-weight:400}

/* ★ 읽는 말이 없는 씬(gap·countdown)은 **한 줄로 접는다.**
   내용이 없는데 정상 행 높이를 먹어서, 번들 하나에 그런 줄이 10개 넘으면 그것만으로
   페이지가 한 장씩 늘어난다. 접어도 정보는 다 남는다(번호·제목·종류). */
.sc.thin{grid-template-columns:18px 1fr;padding:3px 0;font-size:11.5px;
  color:var(--mute);background:transparent}
.sc.thin .hd{font-weight:400;display:flex;gap:7px;align-items:baseline}
.sc.thin .hd .k{display:inline;font-size:10.5px}
.sc.thin .hd::after{content:none}

.schead{display:grid;grid-template-columns:18px minmax(70px,.38fr) 1.62fr;gap:6px;
  border-bottom:2px solid var(--ink);padding:0 0 4px;font-size:11.5px;color:var(--mute)}

/* ★ '조밀 모드' 는 두지 않는다.
   한 장에 2쪽으로 얹는 것은 인쇄 대화상자가 하는 일이고, 사용자가 그때 정한다.
   여기서 미리 줄여 두면 축소가 두 번 겹쳐서 읽을 수 없게 된다.
   페이지를 줄이는 것은 열 비율과 빈 줄 접기로 이미 했다 — 그건 한 쪽 인쇄에서도
   이득이라 항상 켠다. */

@media print{
  body{padding:0;font-size:11.5pt}
  .toolbar{display:none}
  .q,.sc{border-bottom-color:#bbb}
  a{color:inherit;text-decoration:none}
  @page{size:A4;margin:14mm 12mm}
}
"""


def _page(title: str, toolbar: str, body: str, mathjax: bool = True) -> str:
    """공통 껍데기.

    ★ MathJax 는 `pre`·`code` 를 건드리지 않게 제외한다. SQL 박스 안의 `$` 를
      수식으로 먹으면 쿼리가 통째로 사라진다(실제로 겪은 종류의 사고다).
    """
    mj = ""
    if mathjax:
        mj = """
<script>
window.MathJax = {
  tex: { inlineMath: [['$','$'],['\\\\(','\\\\)']], displayMath: [['$$','$$'],['\\\\[','\\\\]']] },
  options: { skipHtmlTags: ['script','noscript','style','textarea','pre','code'] },
  svg: { fontCache: 'global' }
};
</script>
<script src="/static/vendor/tex-svg.js" id="MathJax-script"></script>
"""
    return (
        "<!DOCTYPE html>\n<html lang=\"ko\"><head><meta charset=\"utf-8\">\n"
        f"<title>{_h(title)}</title>\n<style>{_CSS}</style>{mj}</head><body>\n"
        f"{toolbar}\n{body}\n</body></html>\n"
    )


def _toolbar(links: list[tuple[str, str, bool]], note: str) -> str:
    out = ['<div class="toolbar">']
    out.append('<button type="button" onclick="window.print()">인쇄 · PDF 저장</button>')
    for href, label, on in links:
        out.append(f'<a class="{"on" if on else ""}" href="{_h(href)}">{_h(label)}</a>')
    out.append(f'<span class="sp">{_h(note)}</span></div>')
    return "".join(out)


# ─────────────────────────────────────────────────────────────────────────────
# ① 문항 인쇄본
# ─────────────────────────────────────────────────────────────────────────────

def rounds() -> list[int]:
    return sorted({int(p.get("rd_no") or 0) for p in _load_problems()} - {0})


def _table_html(tj) -> str:
    """`table_json` → 표. 형식이 여러 가지라 방어적으로 읽는다."""
    if not tj:
        return ""
    t = tj
    if isinstance(t, str):
        try:
            t = json.loads(t)
        except (ValueError, TypeError):
            return ""
    rows = None
    if isinstance(t, dict):
        rows = t.get("rows") or t.get("data") or t.get("body")
        head = t.get("head") or t.get("header") or t.get("columns")
    else:
        rows, head = t, None
    if not isinstance(rows, list) or not rows:
        return ""
    out = ['<table class="tb">']
    if isinstance(head, list) and head:
        out.append("<tr>" + "".join(f"<th>{_h(c)}</th>" for c in head) + "</tr>")
    for r in rows:
        cells = r if isinstance(r, list) else [r]
        out.append("<tr>" + "".join(f"<td>{_h(c)}</td>" for c in cells) + "</tr>")
    out.append("</table>")
    return "".join(out)


def _one_question(p: dict) -> str:
    n = int(p.get("pr_no") or 0)
    ai = p.get("answer_index")
    ai = int(ai) if isinstance(ai, int) or (isinstance(ai, str) and ai.isdigit()) else -1

    tags = []
    if p.get("sj_name"):
        tags.append(f'<span class="tag">{_h(p["sj_name"])}</span>')
    if p.get("difficulty"):
        tags.append(f'<span class="tag d">난이도 {_h(p["difficulty"])}</span>')
    for t in (p.get("tags_json") or []):
        if isinstance(t, str) and t:
            tags.append(f'<span class="tag">{_h(t)}</span>')
    # ★ 검수 표시를 인쇄물에 남긴다. 종이로 보는 목적의 절반이 '아직 안 본 것' 찾기다.
    if p.get("needs_review"):
        tags.append('<span class="tag d">검수 필요</span>')

    out = ['<div class="q">', '<div class="qh">',
           f'<span class="no">{n}.</span>', "".join(tags),
           f'<span class="key">{_h(p.get("pr_key"))}</span>', "</div>"]

    if p.get("passage"):
        out.append(f'<div class="psg">{_h(p["passage"])}</div>')
    out.append(f'<div class="qt">{_h(p.get("question"))}</div>')
    if p.get("sql_text"):
        out.append(f'<pre class="sql">{_h(p["sql_text"])}</pre>')
    out.append(_table_html(p.get("table_json")))
    for f in (p.get("figures_json") or []):
        if isinstance(f, str) and f:
            out.append(f'<div class="fig"><img src="{_h(_fig_url(f))}" alt="{_h(f)}"></div>')

    ch = p.get("choices_json") or []
    if isinstance(ch, str):
        try:
            ch = json.loads(ch)
        except (ValueError, TypeError):
            ch = []
    out.append('<ol class="ch">')
    for i, c in enumerate(ch):
        mark = _CIRCLE[i] if i < len(_CIRCLE) else str(i + 1)
        cls = " class=\"a\"" if i == ai else ""
        out.append(f'<li{cls}><span class="c">{mark}</span>{_h(c)}</li>')
    out.append("</ol>")

    if p.get("explanation"):
        out.append(f'<div class="ex"><b>해설</b> {_h(p["explanation"])}</div>')
    out.append("</div>")
    return "".join(out)


def questions_html(rd: int | None = None) -> str:
    from core.constants import PD_CODE, PD_LABEL

    ps = _load_problems()
    rs = rounds()
    if rd:
        ps = [p for p in ps if int(p.get("rd_no") or 0) == int(rd)]

    links = [("/print/questions", "전체", rd is None)]
    for r in rs:
        links.append((f"/print/questions?rd={r}", f"{r}회", rd == r))
    links.append(("/print/", "← 목록", False))

    body = [f"<h1>{_h(PD_LABEL)} — 문항 인쇄본</h1>",
            f'<p class="sub">{_h(PD_CODE)} · {len(ps)}문항'
            + (f" · {rd}회차" if rd else f" · {len(rs)}회차 전체")
            + " · 정답과 해설이 함께 나옵니다 (검수용)</p>"]

    for r in ([rd] if rd else rs):
        rp = sorted([p for p in ps if int(p.get("rd_no") or 0) == r],
                    key=lambda x: int(x.get("pr_no") or 0))
        if not rp:
            continue
        nr = sum(1 for p in rp if p.get("needs_review"))
        body.append('<div class="part">'
                    f'<h2>{r}회차</h2>'
                    f'<div class="m">{len(rp)}문항'
                    + (f" · 검수 필요 {nr}건" if nr else "")
                    + "</div></div>")
        body += [_one_question(p) for p in rp]

    note = f"Ctrl+P → 대상을 'PDF로 저장' · 용지 A4 · 배경 그래픽 켜기"
    return _page(f"{PD_LABEL} 문항 인쇄본", _toolbar(links, note), "".join(body))


# ─────────────────────────────────────────────────────────────────────────────
# ② 슬라이드 대본 인쇄본
# ─────────────────────────────────────────────────────────────────────────────

def bundles() -> list[str]:
    d = os.path.join(paths.book_dir(), "05")
    if not os.path.isdir(d):
        return []
    return sorted(n for n in os.listdir(d)
                  if re.fullmatch(r"m\d{2}-\d{1,2}", n)
                  and os.path.isdir(os.path.join(d, n)))


def _scenes(bundle: str) -> tuple[dict, list[dict]]:
    """그 번들의 대본. `script/<번들>_script.json` 이 정본이다.

    ★ `source/slides.json` 은 heading 만 있고 나레이션이 없다. 반대로 script 에는
      둘이 다 있다 — 그래서 script 를 읽는다. 이름이 비슷해 헷갈리는 자리다.
    """
    p = os.path.join(paths.book_dir(), "05", bundle, "script", f"{bundle}_script.json")
    if not os.path.isfile(p):
        return {}, []
    d = json.load(open(p, encoding="utf-8"))
    return d, (d.get("scenes") or [])


def lesson_html(bundle: str | None = None) -> str:
    from core.constants import PD_LABEL

    bs = bundles()
    if bundle and bundle in bs:
        show = [bundle]
    elif bundle:
        show = []
    else:
        show = bs

    links = [("/print/lesson", "전체", bundle is None)]
    for b in bs:
        links.append((f"/print/lesson?b={b}", b, bundle == b))
    links.append(("/print/", "← 목록", False))

    n_sc = 0
    body = [f"<h1>{_h(PD_LABEL)} — 슬라이드 대본 인쇄본</h1>"]
    parts = []
    for b in show:
        meta, sc = _scenes(b)
        if not sc:
            parts.append(f'<div class="part"><h2>{_h(b)}</h2>'
                         '<div class="m">대본이 없습니다 — 이 번들은 아직 만들지 않았습니다.</div></div>')
            continue
        n_sc += len(sc)
        parts.append('<div class="part">'
                     f'<h2>{_h(b)} — {_h(meta.get("round") or "")}</h2>'
                     f'<div class="m">{len(sc)}씬 · 목소리 {_h(meta.get("voice") or "?")}'
                     f' · 속도 {_h(meta.get("speed") or "?")}</div></div>')
        parts.append('<div class="schead"><div>#</div><div>화면(슬라이드)</div>'
                     '<div>읽는 말(나레이션)</div></div>')
        for s in sc:
            cap = bool(s.get("capture", True))
            nr = (s.get("narration_text") or s.get("narration") or "").strip()
            # ★ 읽는 말이 없는 씬(gap·countdown)은 두 칸으로 접는다. 번들 하나에 그런
            #   줄이 10개 넘어서, 접기만 해도 페이지가 눈에 띄게 줄어든다.
            if nr == "":
                parts.append(
                    f'<div class="sc thin">'
                    f'<div class="n">{int(s.get("scene") or 0)}</div>'
                    f'<div class="hd">{_h(s.get("heading"))}'
                    f'<span class="k">{_h(s.get("kind"))}</span></div></div>')
                continue
            parts.append(
                f'<div class="sc{"" if cap else " nocap"}">'
                f'<div class="n">{int(s.get("scene") or 0)}</div>'
                f'<div class="hd">{_h(s.get("heading"))}'
                f'<span class="k">{_h(s.get("kind"))}</span></div>'
                f'<div class="nr">{_h(nr)}</div></div>')

    n_thin = sum(1 for b in show for s in _scenes(b)[1]
                 if not (s.get("narration_text") or s.get("narration") or "").strip())
    body.append(f'<p class="sub">{len(show)}번들 · {n_sc}씬 · '
                "왼쪽이 화면에 나오는 것, 오른쪽이 읽는 말입니다."
                + (f" 읽는 말이 없는 {n_thin}줄(gap·countdown)은 한 줄로 접었습니다."
                   if n_thin else "")
                + "</p>")
    body += parts

    note = "Ctrl+P → 'PDF로 저장' · 용지 A4 (2쪽·양면은 인쇄할 때 정하십시오)"
    return _page(f"{PD_LABEL} 슬라이드 대본", _toolbar(links, note), "".join(body))


# ─────────────────────────────────────────────────────────────────────────────
# ③ 목록
# ─────────────────────────────────────────────────────────────────────────────

def index_html() -> str:
    from core.constants import PD_CODE, PD_LABEL

    try:
        ps = _load_problems()
        n_q, rs = len(ps), rounds()
        nr = sum(1 for p in ps if p.get("needs_review"))
        q_line = (f"{n_q}문항 · {len(rs)}회차"
                  + (f" · <b>검수 필요 {nr}건</b>" if nr else " · 검수 필요 0건"))
        q_ok = True
    except (FileNotFoundError, ValueError) as e:
        q_line, q_ok, rs = _h(str(e).splitlines()[0]), False, []

    bs = bundles()
    body = [f"<h1>{_h(PD_LABEL)} — 인쇄본</h1>",
            f'<p class="sub">{_h(PD_CODE)} · {_h(paths.book_dir())}<br>'
            "파일을 만들지 않습니다. 열 때마다 <b>지금 데이터</b>로 그립니다 — "
            "낡은 종이를 들고 검수할 일이 없습니다.</p>"]

    body.append('<div class="part"><h2>① 문항 인쇄본</h2>'
                f'<div class="m">{q_line}</div></div>')
    if q_ok:
        row = [f'<a href="/print/questions">전체 {len(rs)}회차</a>']
        row += [f'<a href="/print/questions?rd={r}">{r}회</a>' for r in rs]
        body.append('<div class="toolbar" style="position:static;border:0">'
                    + "".join(row) + "</div>")
        body.append('<p class="sub">문제 · 보기 · <b>정답</b> · 해설 · 난이도 · 태그가 '
                    '함께 나옵니다. 한 문항이 페이지에 걸쳐 잘리지 않게 잡아 뒀습니다.</p>')

    body.append('<div class="part" style="page-break-before:auto"><h2>② 슬라이드 대본 인쇄본</h2>'
                f'<div class="m">{len(bs)}번들</div></div>')
    if bs:
        row = [f'<a href="/print/lesson">전체 {len(bs)}번들</a>']
        row += [f'<a href="/print/lesson?b={b}">{b}</a>' for b in bs]
        body.append('<div class="toolbar" style="position:static;border:0;max-height:none">'
                    + "".join(row) + "</div>")
        body.append('<p class="sub">씬마다 <b>화면에 나오는 것</b>과 <b>읽는 말</b>을 '
                    '나란히 둡니다. 캡처하지 않는 씬(카운트다운 등)은 회색입니다.</p>')

    return _page(f"{PD_LABEL} 인쇄본", "", "".join(body), mathjax=False)
