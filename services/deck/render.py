# -*- coding: utf-8 -*-
"""lesson JSON → 슬라이드 HTML. **이 앱의 유일한 슬라이드 HTML 생성기.**

미리보기와 베이크가 **같은 함수**를 쓴다:

    미리보기 : HTMLResponse( render_deck(lesson) )
    베이크   : deck.html.write_text( render_deck(lesson) )   ← 같은 문자열

showcase-agent `render/slides.py` 머리말이 그 이유를 이미 적어 뒀다 —
*"셋이 갈라지면 OK 한 면과 나가는 면이 달라진다."* 그 결론을 그대로 가져왔다.

★ CSS 를 **인라인으로** 심는다. 링크하지 않는다 — 캡처가 `file://` 로 열리므로
  (`deck_capture.py:42`) 상대경로 CSS 는 번들 안에 복사돼야 하고, 그 복사가 낡으면
  조용히 옛 모양으로 찍힌다. `bundle.py:963-976` 의 chmod/PermissionError 방어 코드가
  전부 그 복사 때문에 생긴 것이다.

★ 수식(MathJax)을 넣지 않는다. `/static/vendor/tex-svg.js` 는 http 경로라 `file://`
  에서 안 뜨고, 옆에 복사하면 캡처가 타이포셋을 기다려야 한다(`networkidle` +
  `fonts.ready` 로 부족하고 `MathJax.startup.document.state()` 폴링이 필요하다).
  미리보기에만 켜면 **슬라이드에 없는 수식을 미리보기가 보여준다** — 그게 더 나쁘다.
"""
from __future__ import annotations

import html
import os
import re
from typing import Any, Dict, List, Optional

from . import paginate, theme
from .slidecss import slide_css

CIRCLED = "①②③④⑤"


def esc(s: Any) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


# ── 마크다운(아주 좁게) ─────────────────────────────────────────────────────
# ★ escape 를 먼저 하고 그 뒤에 허용한 것만 되살린다. 순서를 뒤집으면 `<script>` 가
#   그대로 남는다. `exam/lib/md.php` 의 `ex_md_html()` 과 같은 규칙이다.
_IMG = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def md_inline(s: str) -> str:
    out = esc(s)
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"`([^`]+?)`", r"<code>\1</code>", out)
    return out


# ★ 파이프 표. 이것이 없으면 지문이 **원문 그대로** 찍힌다 — 2026-08-12 실측:
#   m01-1 의 45번 지문이 `| 구분 | 질병 발생 | … |---|---|` 로 화면에 나갔다.
#   `_rounds` 의 지문·해설에 마크다운 표가 들어 있는데 슬라이드 렌더러가 `**굵게**` 와
#   `` `코드` `` 만 처리하고 있었다. 표로 그리면 **세로 높이도 크게 줄어든다.**
#
# ★ 한 줄로 이어진 표도 받는다. 집필 출력이 `|a|b| |---|---| |1|2|` 처럼 줄바꿈 없이
#   오는 경우가 있었다(위 45번이 그랬다). 그래서 `|` 로 나누기 전에 구분 행을 찾아
#   행 경계를 복원한다.
_TABLE_SEP = re.compile(r"^[\s|:\-]+$")


def _split_row(line: str) -> List[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def md_table(s: str) -> Optional[str]:
    """마크다운 파이프 표 → `<table>`. 표가 아니면 None."""
    text = str(s or "").strip()
    if text.count("|") < 4:
        return None
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    # 한 줄로 뭉친 경우 — 구분 행(`---`)을 기준으로 열 수를 알아내 다시 자른다.
    if len(lines) == 1:
        # ★ 빈 칸을 먼저 걷어낸다. 행 경계의 `| |` 가 빈 토큰을 하나 만들고, 그것을
        #   세면 열 수가 1 늘어난다(실측: 4열 표가 5열로 잡혀 칸이 어긋났다).
        #   빈 칸이 있는 표를 한 줄로 쓰면 복원할 수 없다 — 그건 줄바꿈이 있어야 한다.
        cells = [c for c in _split_row(lines[0]) if c]
        seps = [i for i, c in enumerate(cells) if _TABLE_SEP.match(c)]
        if not seps or seps[0] < 1:
            return None
        ncol = seps[0]
        body = [c for c in cells if not _TABLE_SEP.match(c)]
        lines = ["|" + "|".join(body[i:i + ncol]) + "|"
                 for i in range(0, len(body), ncol)]
    rows = [_split_row(ln) for ln in lines]
    rows = [r for r in rows if not all(_TABLE_SEP.match(c or "-") for c in r)]
    if len(rows) < 2:
        return None
    head, *body = rows
    th = "".join(f"<th>{md_inline(c)}</th>" for c in head)
    trs = "".join("<tr>" + "".join(f"<td>{md_inline(c)}</td>" for c in r) + "</tr>"
                  for r in body)
    return f"<table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>"


def md_paras(s: str) -> str:
    """빈 줄로 문단을 나눈다. 집필 규약이 '문단으로 분리해 쓴다' 이므로 그것을 그대로 쓴다.

    ★ 문단이 파이프 표면 표로 그린다 — 위 `md_table()` 머리말 참조.
    ★ 문단 **안**의 한 줄 개행은 `<br>` 로 살린다. `br_jamo()` 가 넣은 줄바꿈이
      여기서 사라지면 아무 일도 일어나지 않는다.
    """
    parts = [p.strip() for p in re.split(r"\n\s*\n", str(s or "")) if p.strip()]
    out = []
    for p in parts:
        if tbl := md_table(p):
            out.append(tbl)
        else:
            out.append("<p>" + "<br>".join(
                md_inline(ln) for ln in p.split("\n") if ln.strip()) + "</p>")
    return "".join(out)


def strip_images(s: str) -> str:
    """지문에서 인라인 그림 줄을 뺀다 — 그림은 `assets` 가 따로 들고 있어 중복이다."""
    return _IMG.sub("", str(s or "")).strip()


# ★ `ㄱ. ㄴ. ㄷ. ㄹ.` 항목 앞에서 줄을 바꾼다(2026-08-12 지시: "ㄱ. ㄴ. ㄷ. ㄹ. 앞에
#   엔터가 있어야 해요"). 집필 출력은 이것들을 **한 줄로 이어** 쓴다 — 실측:
#     "ㄱ. 고객 관계형 … 테이블 ㄴ. 웹 서버가 … 로그 ㄷ. 매장에 … 영상 ㄹ. 센서 …"
#   한 줄로 붙어 있으면 어디서 항목이 갈리는지 눈으로 못 찾는다. 세로도 오히려
#   더 먹는다(긴 한 문단이 4줄로 접히는 것보다 4항목 4줄이 짧다).
#
# ★ 문장 첫머리의 `ㄱ.` 은 건드리지 않는다(이미 줄 시작이다). 그리고 자모 뒤에
#   **마침표나 가운뎃점이 붙은 것만** 잡는다 — "그" 로 시작하는 낱말과 섞이지 않게.
_JAMO_ITEM = re.compile(r"(?<=\S)\s+(?=[ㄱ-ㅎ]\s*[.·)]\s)")


def br_jamo(s: str) -> str:
    return _JAMO_ITEM.sub("\n", str(s or ""))


# ── 슬라이드 1장 ────────────────────────────────────────────────────────────
def _head(no: Optional[int], subject: str, difficulty: str, total: int) -> str:
    """머리 — **번호와 난도만.** 첫 장에만 붙는다.

    ★ 과목 칩을 뺐다(2026-08-12 지시: "시작은 번호 난도"). 과목은 회차·편 번호로
      이미 정해져 있어 장마다 되풀이할 값이 아니고, 칩 하나가 세로를 먹는다.
    """
    bits = []
    if no is not None:
        bits.append(f'<span class="qnum">{esc(no)}번</span>')
    if difficulty:
        bits.append(f'<span class="pill pill-orange">{esc(difficulty)}</span>')
    return f'<div class="s-head">{"".join(bits)}</div>'


def _foot(i: int, total: int, title: str) -> str:
    """푸터 — **페이지 번호만.** 끝 장에만 붙는다.

    ★ 제목 줄("모의고사 01회 — 문제 풀이 (1/8)")을 뺐다(2026-08-12 지시: "그 줄이
      없어야 합니다"). 회차·편은 영상 템플릿이 아는 값이고, 캡처한 흰 면 안에서
      되풀이할 이유가 없다. `title` 인자는 호출부를 안 바꾸려고 남겨 둔다.
    """
    return f'<div class="s-foot"><span></span><span>{i} / {total}</span></div>'


def _figure(assets: List[str], asset_dir: str,
            inline_dir: Optional[str] = None) -> str:
    """그림. ★ 카드 안 **첫 자리**에 온다 — CSS `order:-1` 이 위치를 정한다.

    DOM 순서로 강제하지 않는 이유: 분할이 블록 목록을 재배열하므로 DOM 순서를
    믿을 수 없다. CSS 로 못박으면 어느 페이지에서든 그림이 위로 온다.

    ★ `inline_dir` 을 주면 SVG 를 **파일에서 읽어 통째로 심는다.** 베이크가 그렇게
      쓴다. 이유는 캡처가 `05/<번들>/source/deck.html` 을 `file://` 로 열기 때문이다
      — 그때 `src="assets/x.svg"` 는 `source/assets/x.svg` 를 가리키고 그런 폴더는
      없다. 그림이 조용히 안 뜬 채로 72편이 구워진다.
      ★ 번들 안으로 **복사하지 않는다.** `slidecss.py` 머리말이 그 실패를 적어 뒀다:
        "그 복사가 낡으면 조용히 옛 모양으로 찍힌다."
      미리보기는 `inline_dir` 없이 `/book` 마운트로 실제 파일을 가리킨다.
    """
    if not assets:
        return ""
    out = []
    for a in assets:
        name = str(a)
        if inline_dir:
            p = os.path.join(inline_dir, name if name.lower().endswith(".svg")
                             else f"{name}.svg")
            try:
                with open(p, encoding="utf-8") as f:
                    svg = f.read()
            except OSError:
                # ★ 조용히 넘기지 않는다. 그림이 빠진 것을 화면에서 알아야 한다.
                out.append(f'<div class="trunc-note">그림 파일을 찾지 못했습니다: '
                           f'{esc(os.path.basename(p))}</div>')
                continue
            # `<?xml ...?>` 선언과 DOCTYPE 은 인라인에서 쓸 수 없다.
            svg = re.sub(r"<\?xml[^>]*\?>", "", svg)
            svg = re.sub(r"<!DOCTYPE[^>]*>", "", svg, flags=re.I)
            out.append(svg.strip())
        else:
            src = f"{asset_dir}/{name}" if asset_dir else name
            out.append(f'<img class="fig" src="{esc(src)}" alt="">')
    return f'<figure class="diagram">{"".join(out)}</figure>'


def _choices(choices: List[str], answer_index: Optional[int], reveal: bool) -> str:
    """보기 4개. ★ 반드시 다 보인다 — 개수를 줄이거나 접지 않는다."""
    if not choices:
        return ""
    lis = []
    for i, c in enumerate(choices):
        cls = "opt correct" if (reveal and answer_index == i) else "opt"
        mark = CIRCLED[i] if i < len(CIRCLED) else str(i + 1)
        lis.append(f'<div class="{cls}"><span class="cn">{mark}</span>'
                   f'<span>{md_inline(c)}</span></div>')
    return f'<div class="opts">{"".join(lis)}</div>'


# ── 분할 ────────────────────────────────────────────────────────────────────
def _card(pieces_html: str, *, head: str, foot: str, cls: str) -> str:
    """슬라이드 한 장. `cls` 에 이어짐 표시(`cont-top`/`cont-bottom`)가 붙는다.

    ★ 머리·푸터를 **카드 안**에 넣는다(2026-08-12 지시: "시작도 슬라이드 기준
      최상단부터 해도 되고"). 전에는 카드 밖의 띠였고, `.slide` 이 그 자리를
      `--slide-head(50) + --slide-foot(44) + gap(24) = 118px` 로 **모든 장에서**
      잡아 두었다 — 머리도 푸터도 없는 중간 장까지 그랬다.
      안으로 넣으면 그 118px 이 내용으로 돌아오고, 없는 장은 아무 자리도 안 쓴다.
    """
    return (f'<section class="slide content{cls}" style="{theme.style_attr(True)}">'
            f'<div class="qcard">{head}{pieces_html}{foot}</div></section>')


# ★ 장수 상한을 넘으면 **글자를 조여** 담는다 — 더 쪼개지 않는다.
#   규칙(2026-08-12 지시): 해설은 **1바닥**, 문제는 최대 **2바닥**.
#   `.dense` 는 이미 있던 변형이다(`slidecss.py`: `--ts:2.30; --ss:2.05`).
#   글자 크기가 2.67 → 2.30 이므로 높이가 약 0.86배가 되고, 같은 예산에 1/0.86 ≈
#   1.16배가 들어간다. 그것으로 안 되면 그대로 둔다 — 더 조이면 영상에서 안 읽힌다.
DENSE_GAIN = 2.67 / 2.30


def _paged(pieces: List[paginate.Piece], *, first_i: int, total: int, title: str,
           head: str, cap: int = 0, want_foot: bool = True) -> List[str]:
    """조각들을 페이지로 쪼개고 **이어짐 규약**대로 머리·푸터·테두리를 켜고 끈다.

    규약(2026-08-12 사용자 확정):

        첫 장   상단 테두리 O · 머리 O · 하단 테두리 X · 푸터 X
        중간 장 상단 테두리 X · 머리 X · 하단 테두리 X · 푸터 X
        끝 장   상단 테두리 X · 머리 X · 하단 테두리 O · 푸터 O

    한 장으로 끝나면 넷 다 O — 지금까지와 같다.

    ★ 머리·푸터를 **빼는 것만으로는 안 된다.** 빼면 그 자리가 빈 채로 남아 카드가
      위아래로 뜬다. 그래서 `cont-top`/`cont-bottom` 클래스가 CSS 에서 그 띠를
      0 으로 접고 테두리를 없앤다.
    """
    pages = paginate.pack(pieces)
    dense = ""
    # ★ 상한을 넘으면 글자를 조여 다시 담는다(위 `DENSE_GAIN` 머리말).
    if cap and len(pages) > cap:
        tight = paginate.pack(pieces,
                              paginate.BUDGET * DENSE_GAIN,
                              paginate.BUDGET_CONT * DENSE_GAIN)
        if len(tight) < len(pages):
            pages, dense = tight, " dense"
    n = len(pages)
    out: List[str] = []
    for k, pg in enumerate(pages):
        first, last = (k == 0), (k == n - 1)
        cls = dense
        if not first:
            cls += " cont-top"
        if not last:
            cls += " cont-bottom"
        out.append(_card(
            pg.html,
            head=(head if first else ""),
            # ★ 면마다 다르다(2026-08-12 지시): 문제 면은 페이지 번호를 안 쓰고,
            #   해설 면은 번호·난도를 안 쓴다. 그래서 머리·푸터를 각각 껐다 켠다.
            foot=(_foot(first_i + k, total, title) if (last and want_foot) else ""),
            cls=cls))
    return out


def problem_slide(p: Dict[str, Any], *, i: int, total: int, title: str,
                  subject: str, asset_dir: str) -> List[str]:
    """문제 면 — 발문 + (지문) + 보기 4개. 정답을 아직 안 밝힌다.

    ★ **여러 장을 돌려준다.** 안전선을 넘으면 쪼갠다(`_paged`).
    """
    # ★★ 문제 면에는 **그림을 넣지 않는다.** 실측으로 확정: `_rounds` 26/26 문항의
    #   그림 참조가 `explanation` 안에만 있고 `question`/`passage` 에는 0건이다.
    #   이유는 **정답 노출 방지**다 — 도식이 발문 옆에 있으면 답을 암시한다.
    #   (앞선 집필 대화에서 사용자가 명시적으로 정정한 규약이다: *"SVG는 문제/지문이
    #   아니라 해설(explanation)에만"*.)
    #   덕분에 문제 면의 세로 예산이 넉넉해진다 — 발문 + 보기 4개만 담는다.
    passage = strip_images(p.get("passage") or "")
    chs = list(p.get("choices") or [])
    two_col = len(chs) == 4

    pieces: List[paginate.Piece] = []
    q_html = f'<div class="q">{md_inline(p.get("question"))}</div>'
    pieces.append(paginate.Piece(q_html, paginate.h_question(q_html), sticky=True))
    if passage:
        # ★ `ㄱ. ㄴ. ㄷ. ㄹ.` 앞에서 줄을 바꾼다(`br_jamo` 머리말).
        inner = md_paras(br_jamo(passage))
        ph = f'<div class="passage">{inner}</div>'
        # 표는 행 수로 잰다 — 글자 수로 재면 표가 실제보다 낮게 나온다.
        h = (paginate.h_table(inner.count("<tr>")) + paginate.PASSAGE_PAD
             if "<table>" in inner else paginate.h_passage(inner))
        pieces.append(paginate.Piece(ph, h))
    if chs:
        pieces.append(paginate.Piece(
            _choices(chs, p.get("answer_index"), reveal=False),
            paginate.h_choices(chs, two_col)))

    # ★ 보기 4개는 **한 줄(1×4)** 이다(2026-08-12 지시). 전에는 2×2 였다.
    #   16:9 는 가로가 남으므로 한 줄이 공짜이고, 세로 한 줄을 벌어 그림까지 한 장에
    #   당긴다. 4개가 아니면(3개·5개) 한 단으로 세로로 쌓는다.
    cls = " ch4" if two_col else ""
    head = _head(p.get("number"), subject, p.get("difficulty") or "", total)
    # ★ 문제는 최대 **2바닥**(2026-08-12 지시). 넘으면 글자를 조인다.
    # ★ 문제 면은 **하단 페이지 번호를 쓰지 않는다**(2026-08-12 지시).
    return [s.replace('class="slide content', f'class="slide content{cls}', 1)
            for s in _paged(pieces, first_i=i, total=total, title=title,
                            head=head, cap=2, want_foot=False)]


def answer_slide(p: Dict[str, Any], *, i: int, total: int, title: str,
                 subject: str, asset_dir: str,
                 inline_dir: Optional[str] = None) -> List[str]:
    """해설 면 — 정답 배지 + 보기(정답 표시) + 해설.

    ★★ **그림이 여기에 온다.** 문제 면이 아니다 — 실측으로 `_rounds` 26/26 문항의
      그림 참조가 `explanation` 안에만 있다. 이유는 정답 노출 방지다(앞선 집필 대화의
      사용자 정정). 그러니 도식은 해설과 함께 보여야 맞다.

    ★ 보기는 여기에 다시 넣지 않는다. 실측 근거(Chromium 1920×1080, 7번들 140장):
      보기를 반복하면 228px 을 먹어 **예산 652px 의 35%** 가 사라지고, 25장에서 보기가
      카드 밖으로 밀려났다. `bundle.py` 도 같은 결론을 적어 뒀다 —
      *"이어지는 해설 페이지엔 보기 4개를 반복하지 않는다."*

    ★ 그래서 배지에 **정답 보기의 글자까지** 넣는다. 번호만 있으면(정답 ③) 시청자가
      앞 화면을 기억해야 하고, 영상은 되돌려 볼 수 없다.

    ★ **여러 장을 돌려준다.** 해설이 길면 문단 단위로 쪼갠다(`_expl_blocks`).
    """
    ai = p.get("answer_index")
    chs = list(p.get("choices") or [])
    mark = CIRCLED[ai] if isinstance(ai, int) and 0 <= ai < len(CIRCLED) else "?"
    text = md_inline(chs[ai]) if isinstance(ai, int) and 0 <= ai < len(chs) else ""
    badge = (f'<div class="answer-badge">정답 {mark}'
             f'{f" &nbsp;{text}" if text else ""}</div>')
    pieces: List[paginate.Piece] = []
    pieces.append(paginate.Piece(badge, paginate.h_badge(), sticky=True))

    fig = _figure(list(p.get("assets") or []), asset_dir, inline_dir)
    blocks = _expl_blocks(p.get("explanation"))

    if fig:
        # ★ 그림이 있으면 **그림 옆에 해설**을 2단으로 묶어 한 조각으로 만든다
        #   (2026-08-12 지시: "옆에 그림이 뜨고 … 해설은 한바닥에 모아서").
        #   세로로 쌓으면 그림 481px + 해설이 한 장을 넘겨 해설이 두 바닥으로 갈린다.
        #   높이는 **둘 중 큰 쪽**이다 — 나란히 있으므로 합이 아니다. 그리고 해설이
        #   절반 폭으로 좁아져 줄 수가 늘어나므로 그만큼 키운다.
        txt = "".join(b.html for b in blocks)
        h_txt = sum(b.h for b in blocks) * 1.9        # 폭 44% → 줄 수 약 1.9배
        html = (f'<div class="ans-row"><div class="ans-fig">{fig}</div>'
                f'<div class="ans-txt">{txt}</div></div>')
        pieces.append(paginate.Piece(html, max(paginate.h_figure(), h_txt)))
    else:
        # 그림이 없으면 한 단으로 흐른다. 길면 문단 단위로 쪼갠다.
        pieces.extend(blocks)

    head = _head(p.get("number"), subject, p.get("difficulty") or "", total)
    # ★ 해설은 **1바닥**이다(2026-08-12 지시, 여러 번). 넘으면 글자를 조인다.
    # ★ 해설 면은 **상단 문번·난도를 쓰지 않는다**(2026-08-12 지시). 바로 앞 장이
    #   그 문항의 문제 면이므로 번호를 되풀이할 이유가 없다.
    return _paged(pieces, first_i=i, total=total, title=title, head="", cap=1)


def _expl_blocks(text: Any) -> List[paginate.Piece]:
    """해설을 문단·표 단위 조각으로. 각 조각이 따로 다음 장으로 넘어갈 수 있다.

    ★ `<div class="expl">` 로 각각을 감싼다. 한 번만 감싸면 조각이 갈릴 때 여는
      태그와 닫는 태그가 서로 다른 장에 남는다 — 그러면 그 장의 HTML 이 깨진다.
    """
    out: List[paginate.Piece] = []
    for part in re.split(r"\n\s*\n", str(text or "")):
        part = part.strip()
        if not part:
            continue
        if tbl := md_table(part):
            html = f'<div class="expl">{tbl}</div>'
            out.append(paginate.Piece(html, paginate.h_table(tbl.count("<tr>"))))
        else:
            html = f'<div class="expl"><p>{md_inline(part)}</p></div>'
            out.append(paginate.Piece(html, paginate.h_expl(part)))
    return out


def cover_slide(lesson: Dict[str, Any], *, total: int, numbers: List[int]) -> str:
    """표지. ★ 화면에도 문항 범위를 넣는다 — 낭독만 바꾸면 그림과 소리가 어긋난다."""
    rng = (f"{numbers[0]}번부터 {numbers[-1]}번까지" if len(numbers) > 1
           else (f"{numbers[0]}번" if numbers else ""))
    pi, pt = lesson.get("part_index"), lesson.get("part_total")
    part = f"{pt}편 중 {pi}편" if pi and pt else ""
    lead = " · ".join(x for x in (rng, part) if x)
    return (f'<section class="slide cover" style="{theme.style_attr(False)}">'
            f'<div class="eyebrow">{esc(lesson.get("subject") or "")}</div>'
            f'<h1>{esc(lesson.get("title") or lesson.get("chapter") or "")}</h1>'
            f'{f"<p class=lead>{esc(lead)}</p>" if lead else ""}'
            f'</section>')


# ── 덱 전체 ─────────────────────────────────────────────────────────────────
def build_slides(lesson: Dict[str, Any], *, asset_dir: str = "assets",
                 inline_dir: Optional[str] = None) -> List[str]:
    """문항당 문제 면 1장 + 해설 면 1장. 표지 1장.

    ★ **분할이 붙었다**(2026-08-12). 문항당 장수가 고정이 아니다 — 안전선을 넘는
      내용은 다음 장으로 넘어간다(`paginate.pack`). 그래서 장수를 미리 알 수 없고,
      푸터의 `i / total` 을 채우려면 **두 번 만들어야** 한다. 만드는 값이 싸므로
      (문자열 조립뿐) 그 편이 total 을 어림잡는 것보다 정확하다.

    ★ 높이는 Chromium 이 아니라 **추정**으로 잰다(`paginate` 머리말). 실제 넘침은
      캡처 단계가 `overflow` 로 잡아 준다 — 두 겹이다.
    """
    blocks = list(lesson.get("blocks") or [])
    probs = [b for b in blocks if b.get("kind") == "problem"]
    numbers = [int(b.get("number") or 0) for b in probs if b.get("number")]
    subject = lesson.get("subject") or ""
    title = lesson.get("title") or lesson.get("chapter") or ""

    return [h for h, _m in build_pages(lesson, asset_dir=asset_dir,
                                       inline_dir=inline_dir)]


def build_pages(lesson: Dict[str, Any], *, asset_dir: str = "assets",
                inline_dir: Optional[str] = None
                ) -> List[tuple]:
    """`[(html, meta), …]`. **베이크가 script 를 만들 때 쓴다.**

    ★ 덱과 script 를 **한 목록에서** 만들어야 한다. 따로 세면 분할 때 개수가 갈리고,
      그러면 렌더 드라이버가 `deck 슬라이드 ≠ 캡처 씬` 으로 그 자리에서 멈춘다
      (`bundles.py` 의 `ok_1to1`). 드라이버 주석도 같은 것을 적어 뒀다 —
      "페이지 분할로 슬라이드가 늘면 씬·narration_text 도 같이 늘어야 합니다."

    meta = {"kind": "cover"|"problem"|"answer", "number": int|None,
            "page": 이 면의 몇 번째 장(1부터), "pages": 이 면의 총 장수}
    """
    blocks = list(lesson.get("blocks") or [])
    probs = [b for b in blocks if b.get("kind") == "problem"]
    numbers = [int(b.get("number") or 0) for b in probs if b.get("number")]
    subject = lesson.get("subject") or ""
    title = lesson.get("title") or lesson.get("chapter") or ""

    def once(total: int) -> List[tuple]:
        out: List[tuple] = [(cover_slide(lesson, total=total, numbers=numbers),
                             {"kind": "cover", "number": None,
                              "page": 1, "pages": 1})]
        i = 2
        for p in probs:
            no = p.get("number")
            for face, fn in (("problem", problem_slide), ("answer", answer_slide)):
                kw = dict(i=i, total=total, title=title, subject=subject,
                          asset_dir=asset_dir)
                if face == "answer":
                    kw["inline_dir"] = inline_dir
                got = fn(p, **kw)
                for k, s in enumerate(got):
                    out.append((s, {"kind": face, "number": no,
                                    "page": k + 1, "pages": len(got)}))
                    i += 1
        return out

    return once(len(once(0)))


def render_deck(lesson: Dict[str, Any], *, tokens_css: str = "",
                asset_dir: str = "assets", fit: bool = False,
                inline_dir: Optional[str] = None) -> str:
    """덱 HTML 한 장. 미리보기와 베이크가 이 문자열을 공유한다.

    ★ **미리보기 전용 장치를 두지 않는다**(2026-08-12 실측으로 되돌린 결정).
      전에는 상단에 sticky 안내 바(`.gl-bar`)와 경계 적색선을 얹고 "캡처는 `.slide`
      하나씩 element screenshot 을 찍으므로 찍히지 않는다"고 적어 두었다. **틀렸다.**
      element screenshot 은 그 요소의 화면 영역을 찍으므로 위에 겹쳐 그려진 sticky 바가
      **그대로 들어간다.** 실측(`ch12_02_problem.png`):

          y=0        (238,242,247)  ← 1px, 높이가 1081 로 튀던 원인
          y=1..36    ( 30, 38, 55)  ← `.gl-bar` 의 #1e2637 그대로
          y=37~      (255,255,255)  ← 여기서부터 진짜 슬라이드

      적색선(`box-shadow:inset`)도 요소 자신이 그리는 것이라 같이 찍힌다 — 저 검은 띠
      아래에 깔려 안 보였을 뿐이다. 그래서 둘 다 **없앴다.** 캡처 시점에 CSS 로 숨기는
      방법도 있지만, 미리보기와 캡처가 같은 문자열을 공유하는 것이 이 파일의 규약이므로
      **애초에 안 넣는 것**이 규약을 지키는 길이다.
    """
    slides = build_slides(lesson, asset_dir=asset_dir, inline_dir=inline_dir)
    body_cls = "fit" if fit else ""
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<title>{esc(lesson.get('title') or '슬라이드')}</title>
<style>{tokens_css}
{slide_css()}
/* ★ 슬라이드를 틈 없이 죽 이어 놓는다. 이 컨테이너 말고는 **아무것도 얹지 않는다** —
   위에 얹은 것은 element screenshot 에 그대로 들어간다(위 docstring 의 실측). */
.deck{{ display:flex; flex-direction:column; align-items:center;
        gap:0; padding:0; }}
</style></head>
<body class="{body_cls}">
<div class="deck" id="deck" data-generator="xam-local 0.1"
     data-safe-line="{theme.safe_line(True)}"
     data-slides="{len(slides)}">
{''.join(slides)}
</div></body></html>"""
