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
import re
from typing import Any, Dict, List, Optional

from . import theme
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


def md_paras(s: str) -> str:
    """빈 줄로 문단을 나눈다. 집필 규약이 '문단으로 분리해 쓴다' 이므로 그것을 그대로 쓴다."""
    parts = [p.strip() for p in re.split(r"\n\s*\n", str(s or "")) if p.strip()]
    return "".join(f"<p>{md_inline(p)}</p>" for p in parts)


def strip_images(s: str) -> str:
    """지문에서 인라인 그림 줄을 뺀다 — 그림은 `assets` 가 따로 들고 있어 중복이다."""
    return _IMG.sub("", str(s or "")).strip()


# ── 슬라이드 1장 ────────────────────────────────────────────────────────────
def _head(no: Optional[int], subject: str, difficulty: str, total: int) -> str:
    bits = []
    if no is not None:
        bits.append(f'<span class="qnum">{esc(no)}번</span>')
    if subject:
        bits.append(f'<span class="pill pill-teal">{esc(subject)}</span>')
    if difficulty:
        bits.append(f'<span class="pill pill-orange">{esc(difficulty)}</span>')
    return f'<div class="s-head">{"".join(bits)}</div>'


def _foot(i: int, total: int, title: str) -> str:
    return (f'<div class="s-foot"><span>{esc(title)}</span>'
            f'<span>{i} / {total}</span></div>')


def _figure(assets: List[str], asset_dir: str) -> str:
    """그림. ★ 카드 안 **첫 자리**에 온다 — CSS `order:-1` 이 위치를 정한다.

    DOM 순서로 강제하지 않는 이유: 분할이 블록 목록을 재배열하므로 DOM 순서를
    믿을 수 없다. CSS 로 못박으면 어느 페이지에서든 그림이 위로 온다.
    """
    if not assets:
        return ""
    out = []
    for a in assets:
        src = f"{asset_dir}/{a}" if asset_dir else a
        if str(a).lower().endswith(".svg"):
            # SVG 는 <img> 로 걸어도 `file://` 에서 뜬다(같은 폴더에 복사돼 있다).
            out.append(f'<img class="fig" src="{esc(src)}" alt="">')
        else:
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


def problem_slide(p: Dict[str, Any], *, i: int, total: int, title: str,
                  subject: str, asset_dir: str) -> str:
    """문제 면 — 발문 + (지문) + (그림) + 보기 4개. 정답을 아직 안 밝힌다."""
    # ★★ 문제 면에는 **그림을 넣지 않는다.** 실측으로 확정: `_rounds` 26/26 문항의
    #   그림 참조가 `explanation` 안에만 있고 `question`/`passage` 에는 0건이다.
    #   이유는 **정답 노출 방지**다 — 도식이 발문 옆에 있으면 답을 암시한다.
    #   (앞선 집필 대화에서 사용자가 명시적으로 정정한 규약이다: *"SVG는 문제/지문이
    #   아니라 해설(explanation)에만"*.)
    #   덕분에 문제 면의 세로 예산이 넉넉해진다 — 발문 + 보기 4개만 담는다.
    passage = strip_images(p.get("passage") or "")
    body = [
        f'<div class="q">{md_inline(p.get("question"))}</div>',
        f'<div class="passage">{md_paras(passage)}</div>' if passage else "",
        _choices(list(p.get("choices") or []), p.get("answer_index"), reveal=False),
    ]
    # 보기가 4개면 2×2 로 접는다 — 세로 예산을 절반으로.
    ch2 = " ch2" if len(p.get("choices") or []) == 4 else ""
    return (f'<section class="slide content{ch2}" style="{theme.style_attr(True)}">'
            f'{_head(p.get("number"), subject, p.get("difficulty") or "", total)}'
            f'<div class="qcard">{"".join(x for x in body if x)}</div>'
            f'{_foot(i, total, title)}</section>')


def answer_slide(p: Dict[str, Any], *, i: int, total: int, title: str,
                 subject: str, asset_dir: str) -> str:
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
    """
    ai = p.get("answer_index")
    chs = list(p.get("choices") or [])
    mark = CIRCLED[ai] if isinstance(ai, int) and 0 <= ai < len(CIRCLED) else "?"
    text = md_inline(chs[ai]) if isinstance(ai, int) and 0 <= ai < len(chs) else ""
    badge = (f'<div class="answer-badge">정답 {mark}'
             f'{f" &nbsp;{text}" if text else ""}</div>')
    body = [
        badge,
        # 그림은 CSS `order:-1` 로 카드 최상단에 온다(요구사항). 배지보다 위다.
        _figure(list(p.get("assets") or []), asset_dir),
        f'<div class="expl">{md_paras(p.get("explanation"))}</div>',
    ]
    ch2 = ""     # 보기가 없으므로 2×2 접기가 의미 없다
    return (f'<section class="slide content{ch2}" style="{theme.style_attr(True)}">'
            f'{_head(p.get("number"), subject, p.get("difficulty") or "", total)}'
            f'<div class="qcard">{"".join(x for x in body if x)}</div>'
            f'{_foot(i, total, title)}</section>')


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
def build_slides(lesson: Dict[str, Any], *, asset_dir: str = "assets") -> List[str]:
    """문항당 문제 면 1장 + 해설 면 1장. 표지 1장.

    ★ 분할(`paginate`)은 아직 여기서 하지 않는다. 이 단계의 목적은 **기하를 눈으로
      확인하는 것**이고, 분할은 실제 높이를 재야(Chromium) 하므로 다음 단계다.
      그러므로 이 함수가 낸 장수는 **하드 게이트(`.slide` == capture 씬)를 만족하지
      않는다** — 베이크 경로에 붙이기 전에 분할을 넣어야 한다. 그때까지 미리보기 전용.
    """
    blocks = list(lesson.get("blocks") or [])
    probs = [b for b in blocks if b.get("kind") == "problem"]
    numbers = [int(b.get("number") or 0) for b in probs if b.get("number")]
    subject = lesson.get("subject") or ""
    title = lesson.get("title") or lesson.get("chapter") or ""

    total = len(probs) * 2 + 1
    out = [cover_slide(lesson, total=total, numbers=numbers)]
    i = 2
    for p in probs:
        out.append(problem_slide(p, i=i, total=total, title=title,
                                 subject=subject, asset_dir=asset_dir))
        i += 1
        out.append(answer_slide(p, i=i, total=total, title=title,
                                subject=subject, asset_dir=asset_dir))
        i += 1
    return out


def render_deck(lesson: Dict[str, Any], *, tokens_css: str = "",
                asset_dir: str = "assets", fit: bool = False) -> str:
    """덱 HTML 한 장. 미리보기와 베이크가 이 문자열을 공유한다."""
    slides = build_slides(lesson, asset_dir=asset_dir)
    body_cls = "fit" if fit else ""
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<title>{esc(lesson.get('title') or '슬라이드')}</title>
<style>{tokens_css}
{slide_css()}
/* 미리보기 전용 — 캡처는 `.slide` 하나씩 element screenshot 을 찍으므로
   이 스크롤 컨테이너는 캡처 결과에 영향을 주지 않는다. */
.deck{{ display:flex; flex-direction:column; align-items:center;
        gap:24px; padding:24px; }}
</style></head>
<body class="{body_cls}">
<div class="deck" id="deck" data-generator="xam-local 0.1"
     data-safe-line="{theme.safe_line(True)}"
     data-slides="{len(slides)}">
{''.join(slides)}
</div></body></html>"""
