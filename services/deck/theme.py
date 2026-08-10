# -*- coding: utf-8 -*-
"""슬라이드 기하 — **숫자의 단일 소유자.**

CSS 와 파이썬이 같은 값을 써야 한다. 안전선을 두 곳에서 계산하면 식이 갈리고,
그 차이는 영상을 보고 나서야 드러난다(캡션이 보기 위에 겹친 상태로 유튜브까지 갔다).
그래서 여기서 계산해 ① CSS 변수로 심고 ② 파이썬 분할기가 같은 값을 읽는다.

★ 계층 규약: FastAPI 를 import 하지 않는다(services/* 공통).

── 실측으로 확정된 수치 (`05/m01-1/source/_deck.css` · `bundle.py:488-522`) ──
  슬라이드      1920 × 1080 고정 (캡처 결정성 — `deck_capture.py` 뷰포트와 같다)
  바깥 패딩     96px (상하)
  머리 띠       50px  (번호·과목 칩)
  발 띠         44px  (진행·브랜드)
  띠 여백       24px
  → 본문 가용   1080 − 96×2 − (50+44+24) = **770px**
  `.qcard` 안쪽 패딩 56×2 + 테두리 3×2 = 118 → 카드 내부 **652px**

  이 두 숫자(770 / 652)가 `bundle.py:495` 의 `availAll` 검산과 일치한다. 옮긴 것이지
  다시 구한 것이 아니다.
"""
from __future__ import annotations

import os
from typing import Dict

from core.constants import AXEXAM_DIR

# ★ 사이트의 색·타이포 토큰. 슬라이드가 **같은 정의**를 읽는다 — 값을 복사하지 않는다.
#   `present/style.css` 첫머리가 이 파일을 `@import` 하므로 사이트와 소유자가 하나다.
TOKENS_CSS = os.path.join(AXEXAM_DIR, "assets", "present", "tokens.css")


def tokens_css() -> str:
    """토큰 CSS 본문. ★ 파일이 없으면 **멈춘다** — 하드코딩 색으로 폴백하지 않는다.

    폴백하면 슬라이드가 사이트와 조용히 갈리고, 사람은 영상을 보고 나서 안다.
    """
    if not os.path.isfile(TOKENS_CSS):
        raise FileNotFoundError(
            f"색 토큰을 찾지 못했습니다: {TOKENS_CSS}\n"
            "`axexam/assets/present/tokens.css` 가 있어야 슬라이드가 사이트와 같은 "
            "색으로 나옵니다. (style.css 의 :root 블록을 분리한 파일입니다.)")
    with open(TOKENS_CSS, encoding="utf-8") as f:
        return f.read()

# ── 캔버스 ──────────────────────────────────────────────────────────────────
SLIDE_W = 1920
SLIDE_H = 1080
PAD = 96                # 바깥 패딩(상하좌우)

HEAD_H = 50             # 머리 띠 — 번호 · 과목 · 난이도 칩
FOOT_H = 44             # 발 띠 — 진행 표시
BAND_GAP = 24           # 띠와 본문 사이

# 카드 내부로 들어갈 때 잃는 높이
CARD_PAD = 56           # 상하 각각
CARD_BORDER = 3

# ★ 안전 여유. `bundle.py:611` 의 `_fits` 가 `used <= availAll - SAFETY` 로 쓰는 값과
#   같아야 한다. 여유가 없으면 폰트 렌더 차이(1~2px)로 캡처에서만 넘친다.
SAFETY = 12


def avail(has_card: bool = True) -> int:
    """본문에 쓸 수 있는 높이(px). 카드 유무로 갈린다."""
    body = SLIDE_H - PAD * 2 - (HEAD_H + FOOT_H + BAND_GAP)
    return body - (CARD_PAD * 2 + CARD_BORDER * 2) if has_card else body


def safe_line(has_card: bool = True) -> int:
    """넘침 판정선. 캡처 쪽(`deck_capture.py`)이 `data-safe-line` 으로 읽는 값이다.

    ★ 캡처가 CSS 로 재유도하지 않는다 — 덱이 선언한 값을 읽는다. 두 곳에서 계산하면
      식이 갈린다(계획 2-F 의 결론).
    """
    return avail(has_card) - SAFETY


# ── 스케일 ──────────────────────────────────────────────────────────────────
# 사이트 카드(746px) ↔ 슬라이드 캔버스(1808px = 1920 − 96×2) 를 잇는 두 값.
# **하나가 아니라 둘인 이유:**
#   글자는 h.264 를 타면서 뭉갠다 → 비례보다 크게 (15px → 40px, ×2.67)
#   여백은 1080px 예산을 먹는다  → 비례보다 작게 (22px → 56px, ×2.40)
TEXT_SCALE = 2.67
SPACE_SCALE = 2.40

# ★ 도식 높이 상한 비율. **선택이 아니다.**
#   `_paginate_one` 은 블록 하나를 쪼갤 수 없다. 도식이 자기 페이지에서도 넘치면
#   `bundle.py:800-803` 이 도식을 `.trunc-note` 안내문으로 **교체한다** —
#   작아지는 것이 아니라 사라진다.
#
# ★ 0.62 → 0.45. **예산에서 거꾸로 계산한 값이다**(m04-3 실측, Chromium 1920×1080):
#
#     안전선 640px 에 문제 면이 담아야 하는 것
#       발문 60 + 보기 2×2 228 + 자식 간격 48        = 336px  ← 줄일 수 없다
#       → 그림에 남는 예산 640 − 336                 = 304px
#       → 304 / 652(카드 내용 영역)                  ≈ 0.466 → 안전하게 0.45
#   그 뒤 보기 패딩을 조여 190px 로 줄이고(228→190), 발문 2줄(120px)을 넣기 위해
#   0.42(274px)로 한 번 더 내렸다: 274 + 120 + 190 + 40 = 624 ≤ 640 ✓
#
#   0.62 로 두면 그림이 404px 이 되어 합계 742px — 안전선을 102px 넘긴다.
#   "그림을 상단부터 꽉" 과 "보기 4개 반드시 다 보여야" 가 상충하는 지점이 정확히 여기다.
#   해소: 그림은 **가로를 꽉 채우고 상단 띠를 차지하되** 세로로 보기를 밀어내지 않는다.
#   비율을 더 올리려면 보기를 자르는 수밖에 없고, 그건 요구사항 위반이다.
#
# ★ 발문이 2~3줄로 길어지면 이 상한으로도 안 들어간다. 그때는 그림을 더 줄이는 것이
#   아니라 **페이지를 쪼갠다**(사용자 결정). 그래서 분할이 선택이 아니다.
FIGURE_MAX_RATIO = 0.42


def css_vars(has_card: bool = True) -> Dict[str, str]:
    """`.slide` 인라인 스타일로 심을 변수. CSS 가 이것만 보고 계산한다."""
    a = avail(has_card)
    return {
        "--slide-w": f"{SLIDE_W}px",
        "--slide-h": f"{SLIDE_H}px",
        "--slide-pad": f"{PAD}px",
        "--slide-head": f"{HEAD_H}px",
        "--slide-foot": f"{FOOT_H}px",
        "--slide-band-gap": f"{BAND_GAP}px",
        "--slide-avail": f"{a}px",
        "--slide-safe": f"{safe_line(has_card)}px",
        "--ts": f"{TEXT_SCALE}",
        "--ss": f"{SPACE_SCALE}",
        "--fig-max": f"{int(a * FIGURE_MAX_RATIO)}px",
    }


def style_attr(has_card: bool = True) -> str:
    return ";".join(f"{k}:{v}" for k, v in css_vars(has_card).items())
