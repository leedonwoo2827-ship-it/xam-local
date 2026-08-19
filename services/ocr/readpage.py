# -*- coding: utf-8 -*-
"""**판독** — 페이지 PNG 를 읽어 `data/ocr_draft/<src>_pNNN.json` 을 쓴다.

지금까지 이 일은 **사람이 Claude Code 창에 말로 시켰다.** 그래서 `services/ocr/`
머리말에 "판독은 이 앱이 하지 않는다 — LLM 의존성이 없다" 고 적혀 있었다. 그 전제가
깨진 지 오래다: **문항 집필이 이미 같은 통로를 쓴다**(`services/authoring/provider.py`
→ `claude_agent_sdk` → Claude Code CLI). 앱은 이미 LLM 에 의존하고, 판독만 창 밖에
두면 품목마다 사람이 같은 말을 151번 해야 한다.

  00/*.pdf  ──[PDF 렌더]──▶  data/raw_pages/<src>/page_NNN.png
                            └──[스캔(판독)]──▶  data/ocr_draft/<src>_pNNN.json   ← 여기
                                              └──[확정]──▶  01/{RR}-{NN}.md

★ **집필과 같은 provider 를 쓴다.** 새 API 키도 `anthropic` 패키지도 필요 없다.
  `Read` 툴이 PNG 를 읽으므로 이미지를 base64 로 나를 필요도 없다 — 경로만 준다.

★ **모델이 파일을 쓰지 않는다.** `ClaudeAuthor` 가 Write/Edit 를 금지한다. 받은 dict 를
  이 모듈이 검증한 뒤 `draft.save()` 로 쓴다 — 확정(01/)에는 손이 닿지 않는다.

★ 초안은 **사람이 검수할 재료**다. 확실하지 않은 것을 지어내지 말고 비워 두게 한다 —
  빈 칸은 화면에서 눈에 띄지만, 그럴듯하게 채워진 오답은 검수를 통과한다.
"""
from __future__ import annotations

import os
import re
import threading
from typing import Any, Callable, Dict, Optional

from services.authoring.provider import ClaudeAuthor
from services.ocr import draft, project

# 보기 글리프 — `finalize.CIRCLED` 와 같아야 한다. 파서가 이 글자로만 보기를 센다.
GLYPHS = "①②③④⑤"

SYSTEM = """당신은 자격증 기출문제집 스캔 페이지를 판독합니다.

주어진 PNG 를 Read 로 읽고, 그 페이지에 있는 문항만 뽑아 구조화합니다.

■ 판독 규칙

- **보기는 반드시 `①②③④`(원문자)로 번호를 매긴다.** 원본이 `1. 2. 3. 4.` 로
  인쇄돼 있어도 원문자로 옮긴다. 이 표기가 아니면 앱의 파서가 보기를 세지 못한다.
- 보기 텍스트에는 번호를 **포함하지 않는다.** `choices` 는 번호를 뗀 본문만 담는다.
- 발문(`stem`)은 문제 문장 그대로. 보기·지문·해설을 섞지 않는다.
- **지문 자료는 `assets` 로 뺀다.** 발문과 보기 사이에 있는 자료(표·SQL·데이터·글상자)를
  `assets` 배열에 담고, `jimun` 에는 그 자리를 가리키는 토큰만 둔다.

    assets: [{"type": "table", "title": "속성의 종류", "md": "| 속성 | 주요 내용 |
|---|---|
…"}]
    jimun : "{{t-1}}"

  `type` 은 다음 중 하나다:
    table  표          → `md` 에 마크다운 표.
                       ★ **셀 안의 `|` 는 `\\|` 로 이스케이프한다.** SQL 문법의 OR 표기
                         (`EXTRACT('YEAR' \\| 'MONTH' \\| 'DAY' from d)`)가 그대로 들어가면
                         열 구분자로 먹혀 표가 무너진다(실측 31번)
    sql    SQL 박스    → `text` 에 SQL 본문(백틱 없이)
    text   글상자      → `text` 에 본문. `·` 로 시작하는 서술 목록이 여기다
    latex  수식        → `text` 에 LaTeX 본문($ 없이)
    figure 그림        → `note` 에 무엇을 그린 그림인지 + `bbox` 에 잘라낼 영역

  토큰 이름은 `type` 첫 글자 + 일련번호다 — table→`t-1`, sql→`b-1`, text→`x-1`,
  latex→`m-1`, figure→`p-1`. 자료가 여러 개면 `t-1` `t-2` 처럼 늘린다.
  ★ 자료가 없으면 `assets` 는 빈 배열, `jimun` 은 빈 문자열이다.
  ★ 발문·보기·해설 안에 자료를 그대로 펼쳐 넣지 않는다 — 그러면 사람이 손으로
    떼어내야 한다(실측: 발문 칸이 비어 보이고 지문이 통째로 사라진 것처럼 보였다).
- **해설**(`explanation`)은 그 페이지에 해설이 인쇄된 경우에만. 없으면 빈 문자열.

■ 자료가 지문인지 해설인지 — **보기를 기준으로 갈린다**

- 보기(①②③④) **앞**에 있는 자료 → **지문**. `assets` 에 담고 `jimun` 에 토큰.
- 보기 **뒤**에 있는 자료 → **해설**. `assets` 에 담고 `explanation` 안에 토큰을 둔다.
  `placement` 를 `"해설"` 로 적는다.
- 해설의 설명 문장은 `explanation` 에 그대로 쓰고, 표·SQL 만 자산으로 뺀다.

  실측 사고: `속성의 특성에 따른 분류로 올바른 것은?` 문항에서 보기 뒤의
  `속성의 종류` 표를 지문으로 보내 **해설이 빈 채로** 저장됐다. 이 책은 문제와 해설이
  같은 면에 인쇄되므로, 위치로 갈라야 한다.
- 정답(`answer`)은 원문자 하나. 페이지에 정답 표시가 없으면 **빈 문자열로 둔다.**

■ 쪽을 걸친 문항 — **시작한 쪽이 갖는다**

이 책은 문항이 면 경계에서 잘린다. 그래서 **이어지는 면 이미지도 함께** 준다.

- 이 면에서 **시작한** 문항은 다음 면에 있는 **보기·지문 자료·해설·정답까지 전부 가져와
  완성한다.** 반쪽으로 담지 않는다. 그리고 그 문항에 `spans_next: true` 를 적는다.
  (실측 사고: 보기와 결과표만 가져오고 **해설을 비운 채** 저장했다 — 다음 면을 읽을 때
   그 해설은 '앞 면 문항의 것' 이라 또 버려져 어디에도 남지 않는다)
- 이 면의 **첫 문항이 앞 면에서 이어져 온 것**이면 **담지 않는다.** 앞 면이 이미 담았다.
  `notes` 에 "N번은 앞 면에서 시작" 이라고만 적는다.
- 다음 면에서 **새로 시작하는** 문항은 담지 않는다. 그 면을 읽을 때 담는다.

  실측: 18번은 발문·지문이 5쪽, 보기·결과표·해설이 6쪽이었다. 옛 확정본도
  `source_pages: [5, 6]` 으로 **한 문항**이었다 — 쪼개면 둘 다 반쪽이 된다.

■ 충실도 — 무엇을 그대로 옮기고 무엇은 느슨해도 되는가

- **발문 · 지문 · 보기 · 정답은 인쇄된 그대로 옮긴다.** 맞춤법·대소문자·띄어쓰기까지.
- **오식으로 보이는 것도 고치지 않는다.** `TRUCATE`(TRUNCATE), `COL`(COL1) 같은 것을
  실제로 만났다. ★ 그것이 **보기를 틀리게 만들려는 출제 의도**일 수 있다 — 고치면
  정답이 바뀐다. 오식이라고 판단되면 `note` 에 적어 두고 본문은 그대로 둔다.
- **해설은 느슨해도 된다.** 축약하거나 풀어 써도 상관없다(2026-08-18 지시). 이 자료는
  키워드와 출제 경향을 참고하는 데 쓰이므로 해설의 글자 일치는 목적이 아니다.
  흐려서 못 읽는 대목은 `?` 로 남기기보다 **읽히는 요지로 옮기는 편이 낫다.**
- 그래도 **없는 것을 만들지는 않는다.** 인쇄돼 있지 않은 표 제목·정답·해설을 지어내지
  않는다(실측: 제목이 없는 표에 「3층 스키마」를 지어낸 적이 있다).

■ 지어내지 않는다

- 페이지가 잘려 문항의 일부만 보이면 보이는 부분만 담고 `note` 에 무엇이 잘렸는지 적는다.
- 읽을 수 없는 글자는 `?` 로 남기고 `note` 에 적는다.
- **해설·정답을 추론해서 채우지 않는다.** 빈 칸이 오답보다 낫다 — 사람이 검수한다.
- ★ **빈칸을 채우지 않는다.** 발문·지문에 `(  )` · `(   )` · `( ㄱ )` 처럼 **비워 둔
  자리**가 있으면 **그 모양 그대로**, 괄호 안 공백 길이까지 옮긴다. 문항 전체를 보면 답이
  보이므로 '읽어낸 것' 이라고 착각하기 쉬운 자리다 — 채우면 **문제가 성립하지 않는다**
  (답이 발문에 적혀 버린다).

■ 이 책의 기호 세 가지 — 섞지 않는다

    (   )   **빈칸.** 답을 채워야 하는 자리. 공백 길이가 원본마다 다르다 — 그대로 옮긴다
    [   ]   **캡션(제목).** `[Mytest]` · `[결과]` 처럼 표·블록의 이름이다
    <>      **SQL 부등호.** `WHERE A.V1 <> B.V1` — 빈칸이 아니다

  ★ `<>` 를 빈칸으로 오해해 비우면 SQL 이 깨진다. 반대로 캡션 자리를 `(  )` 로 옮기면
    빈칸 문제로 읽힌다. 실측으로 세 기호가 한 회차 안에 다 나온다.
- 문항이 없는 페이지(표지·목차·정답표만 있는 면)는 `questions` 를 빈 배열로 둔다.
  정답표만 있으면 그 줄을 `answer_key_line` 에 그대로 옮긴다.

■ 난이도(`difficulty`)

- `하` · `중` · `상` 중 하나. **기출 문항이 실제로 어느 수준인지** 매긴다.
- 기준(루브릭)은 이 프롬프트 끝에 붙는다. **문제집마다 다르다** — 그 기준만 쓴다.
- 이 값은 나중에 **집필이 쓴다.** 기출이 실제 시험보다 쉬우면 그만큼 올려 출제하도록
  판단하는 근거다. 그래서 **후하게 매기지 않는다** — 실제로 쉬운 문항은 `하` 다.

■ 그림 좌표(`bbox`)

- `figure` 자산에는 **`bbox: [x, y, w, h]`** 를 넣는다. 페이지 PNG 의 **픽셀 좌표**이고
  좌상단이 (0,0) 이다. 이 좌표로 잘라 문제집에 실린다.
- Read 로 이미지를 열면 크기를 알 수 있다. **그림을 넉넉히 감싸되 발문·보기 글자는
  넣지 않는다.** 표제(「고객」·「사용자 계정」 같은 박스 이름)는 그림의 일부이니 포함한다.
- ★ 그림이 **다음 면**에 있으면 `page` 에 그 면 번호를 넣는다. 해설 그림이 면을 넘어가는
  문항이 있다(발문·보기는 이 면, 해설 그림은 다음 면). 좌표는 그 면의 픽셀이다.
  `page` 를 빼면 이 면에서 같은 자리를 잘라 **엉뚱한 그림이 실린다.**
- 좌표를 정할 수 없으면 `bbox` 를 **넣지 않는다.** 빈 채로 두면 화면이 「영역 미지정」으로
  표시하고 사람이 드래그한다 — 엉뚱한 데를 자른 그림보다 낫다.
- `note` 는 그림 설명이다. 자막·대체텍스트로 쓰이므로 무엇이 그려졌는지 적는다.
  예: `ERD: 고객(그룹ID FK) — 사용자 계정(사용자ID, 사용자 이름, 그룹ID FK)`

■ 회차

- 페이지에 회차 표시(`제1회`·`01회`·`최신 기출문제 01회`)가 있으면 `round` 에 숫자만,
  `round_label` 에 표기 그대로 넣는다. 없으면 둘 다 비운다 — 앱이 페이지 지도로 채운다.
"""

SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["questions", "ocr_text", "answer_key_line", "notes"],
    "properties": {
        "round": {"type": ["integer", "null"], "description": "회차 숫자. 없으면 null"},
        "round_label": {"type": "string", "description": "회차 표기 그대로. 없으면 빈 문자열"},
        # ★ 페이지 전문. 화면 왼쪽 「OCR 원문」 칸이 이것을 띄운다 — 사람이 카드와
        #   대조하는 근거라서, 구조화에 실패한 부분도 여기엔 남아 있어야 한다.
        "ocr_text": {"type": "string", "description": "페이지 글자 전문(구조화 전 원문)"},
        "answer_key_line": {"type": "string", "description": "정답표 줄. 없으면 빈 문자열"},
        "notes": {"type": "string", "description": "판독 중 의심스러웠던 것"},
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["question_no", "stem", "choices"],
                "properties": {
                    "question_no": {"type": "integer"},
                    "stem": {"type": "string", "description": "발문. 자료는 넣지 않는다"},
                    "jimun": {"type": "string",
                              "description": "지문 자리 — 자산 토큰만. 자료가 없으면 빈 문자열"},
                    "assets": {
                        "type": "array",
                        "description": "지문 자료. 표·SQL·글상자·수식·그림",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["type"],
                            "properties": {
                                "type": {"enum": ["table", "sql", "text", "latex", "figure"]},
                                "title": {"type": "string"},
                                "md": {"type": "string", "description": "type=table 일 때"},
                                "text": {"type": "string",
                                         "description": "type=sql/text/latex 일 때"},
                                "note": {"type": "string", "description": "type=figure 일 때 — 그림 설명"},
                                "bbox": {"type": "array", "items": {"type": "integer"},
                                         "minItems": 4, "maxItems": 4,
                                         "description": "type=figure 일 때 [x,y,w,h] 픽셀"},
                                "page": {"type": "integer",
                                         "description": "type=figure 일 때 — 이 좌표가 있는 면. 다음 면의 그림일 때만 넣는다"},
                                "placement": {"enum": ["지문", "해설"],
                                              "description": "이 자료가 놓이는 자리. 기본 지문"},
                            },
                        },
                    },
                    "choices": {"type": "array", "items": {"type": "string"},
                                "minItems": 2, "maxItems": 5},
                    "answer": {"type": "string", "description": "①②③④⑤ 중 하나. 없으면 빈 문자열"},
                    "explanation": {"type": "string"},
                    "difficulty": {"enum": ["하", "중", "상"]},
                    "spans_next": {"type": "boolean",
                                   "description": "다음 면까지 걸친 문항이면 true"},
                    "note": {"type": "string", "description": "잘림·판독불가 메모"},
                },
            },
        },
    },
}


_TOKEN_RE = re.compile(r"\{\{[A-Za-z]+-\d+\}\}")


def _carry_round(src: str, page: int, questions: list) -> tuple:
    """앞 페이지의 회차를 이어받는다. 문항번호가 되돌아갔으면 다음 회차다.

    ★ `stamp_rounds()` 와 같은 규칙이다(번호 리셋이 경계). 다만 여기는 **판독 직후
      그 페이지 하나**를 위한 것이라, 앞 페이지 초안만 보고 정한다.
    """
    prev = None
    for p in range(int(page) - 1, 0, -1):
        d = draft.load(src, p)
        if d and (d.get("questions") or []) and d.get("round"):
            prev = d
            break
    if not prev:
        return None, None
    rn = int(prev["round"])
    prev_max = max(q["question_no"] for q in prev["questions"])
    nos = [q["question_no"] for q in (questions or []) if q.get("question_no")]
    if nos and min(nos) <= prev_max:
        rn += 1                                  # 번호가 되돌아갔다 → 새 회차
    return rn, project.round_label(rn) or ""


def _system() -> str:
    """판독 지침 + **그 폴더의 난이도 루브릭.**

    ★ 루브릭을 코드에 박지 않는다 — 문제집마다 다르다(2026-08-18 지시). `book.json` 의
      `difficulty_rubric` 을 읽어 붙인다. 없으면 붙이지 않고, 그러면 모델이 스스로
      판단하므로 회차 간에 흔들린다 — 그래서 폴더마다 채워 두는 것이 맞다.
    """
    rub = project.book_config().get("difficulty_rubric") or []
    if not rub:
        return SYSTEM
    if isinstance(rub, dict):
        # 시험정보의 실제 모양 — {"하": "…", "중": "…", "상": "…"}
        lines = [f"{k} : {v}" for k, v in rub.items()]
    else:
        lines = rub if isinstance(rub, list) else [str(rub)]
    head = chr(10) * 2 + "■ 이 문제집의 난이도 루브릭" + chr(10) * 2
    return SYSTEM + head + chr(10).join(str(x) for x in lines)


def _bbox(raw, size: tuple) -> list | None:
    """모델이 낸 `[x,y,w,h]` 를 검증한다. 못 믿을 값이면 **버린다**(None).

    ★ 버리는 쪽이 안전하다. 좌표가 없으면 화면이 「영역 미지정」으로 보여 주고 사람이
      드래그한다 — 눈에 띈다. 반대로 엉뚱하게 잘린 그림은 검수를 통과해 확정본에 굳는다.

    ★ 페이지 밖으로 나가면 `PIL.crop` 이 검은 여백을 채워 조용히 이상한 그림을 만든다.
      그래서 경계로 물린다(clamp) — 살짝 넘친 것은 살리고, 아예 빗나간 것은 버린다.
    """
    if not (isinstance(raw, (list, tuple)) and len(raw) == 4):
        return None
    try:
        x, y, w, h = (int(v) for v in raw)
    except (TypeError, ValueError):
        return None
    W, H = size
    if w <= 0 or h <= 0 or x < 0 or y < 0:
        return None
    if W and H:
        if x >= W or y >= H:
            return None                       # 시작점이 페이지 밖 — 좌표계를 오해한 것
        w, h = min(w, W - x), min(h, H - y)
        # 너무 작으면 글자 한 줄을 집은 것이다. 실측 옛 크롭은 1004×619(페이지 61%×26%).
        if w < W * 0.08 or h < H * 0.02:
            return None
    return [x, y, w, h]


def _detok(text: str) -> str:
    """모델이 본문에 박아 넣은 자산 토큰을 뗀다.

    ★ 토큰 자리는 **우리가 정한다**(`_assets`). 모델이 쓴 것을 남겨 두면 같은 토큰이
      두 번 박힌다 — 실측으로 해설이 `{{t-1}}

{{t-1}}` 이 됐다.
    """
    return _TOKEN_RE.sub("", text or "").strip()


def _table_md(md: str, title: str = "") -> str:
    """표를 **성립하는 마크다운**으로 되맞춘다.

    ★ 지침으로는 안 잡힌다. 같은 페이지를 두 번 읽었을 때 한 번은 구분선(`|---|`)이 있고
      한 번은 없었다(2026-08-18 실측). 구분선이 없으면 마크다운이 표로 렌더되지 않고
      파이프가 글자로 나간다 — 화면·인쇄본·영상 슬라이드가 다 깨진다.

    하는 일은 셋뿐이다: 줄마다 양끝 파이프를 채우고, 열 수를 첫 줄에 맞추고,
    구분선이 없으면 둘째 줄에 끼운다. 셀 내용은 건드리지 않는다.
    """
    lines = [ln.strip() for ln in (md or "").splitlines() if ln.strip()]
    if not lines:
        return ""
    rows = []
    for ln in lines:
        # ★ 구분선은 `-` 가 있어야 한다. 없으면 **빈 행**이다 —
        #   원본 표에 값이 없는 행이 있다(실측 32번). 그걸 구분선으로 보고 버리면
        #   표에서 한 줄이 조용히 사라진다.
        if ESC_PIPE not in ln and "-" in ln and re.fullmatch(
                r"[\s:\-\|]+", ln.strip(PIPE)):
            continue
        # ★ `\|` 는 **셀 내용**이다(구분자가 아니다). SQL 문법의 OR 표기
        #   `EXTRACT('YEAR' \| 'MONTH' \| 'DAY' from d)` 가 한 셀인데, 그냥 쪼개면
        #   4열이 되고 표가 무너진다 — 앞줄에 맞춰 열을 늘리는 보정이 그걸 더 키웠다(실측 31번).
        cells = [c.strip() for c in re.split(r'(?<!\\)\|', ln.strip(PIPE))]
        rows.append(cells)
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    out = []
    for i, r in enumerate(rows):
        r = r + [""] * (width - len(r))
        out.append("| " + " | ".join(r) + " |")
        if i == 0:
            out.append("|" + "|".join(["---"] * width) + "|")
    return chr(10).join(out)


# 자산 종류 → 토큰 접두. `static/js/ocr.js` 의 ASSET_KINDS 와 같아야 한다
# (표 t · SQL b · 텍스트 x · 수식 m · 그림 p).
_ASSET_PREFIX = {"table": "t", "sql": "b", "text": "x", "latex": "m", "figure": "p"}
JOIN = chr(10) * 2
PIPE = chr(124)
ESC_PIPE = chr(92) + chr(124)      # 표 셀 안의 파이프 — 구분자가 아니다          # 토큰 사이의 빈 줄


def _assets(raw: list, size: tuple = (0, 0),
            page: int = 0) -> tuple[dict, str, str]:
    """모델이 낸 자산 배열 → `({토큰id: 자산}, 지문 토큰, 해설 토큰)`.

    ★ 토큰 이름을 **여기서 매긴다.** 모델에게 맡기면 `{{t-1}}` 을 지문에 쓰고 자산은
      `t1` 로 내는 식으로 어긋난다 — 그러면 화면이 토큰을 펼치지 못하고 `{{t-1}}` 이
      글자로 남는다. 지문에 온 토큰은 무시하고 순서대로 다시 붙인다.

    ★ 그림에는 `bbox` 를 넣지 않는다. 크롭 좌표는 사람이 스캔에서 드래그해 정한다
      (`finalize` 가 그 좌표로 잘라 `01/images/` 에 넣는다).
    """
    out: dict = {}
    order: list = []          # 지문에 놓이는 자산
    expl: list = []           # 해설에 놓이는 자산
    seen: dict = {}
    for a in raw:
        t = str((a or {}).get("type") or "").strip()
        if t not in _ASSET_PREFIX:
            continue
        pre = _ASSET_PREFIX[t]
        seen[pre] = seen.get(pre, 0) + 1
        aid = f"{pre}-{seen[pre]}"
        item: dict = {"type": t}
        if t == "table":
            item["title"] = str(a.get("title") or "")
            item["md"] = _table_md(str(a.get("md") or ""))
        elif t == "figure":
            item["note"] = str(a.get("note") or "figure")
            bb = _bbox(a.get("bbox"), size)
            if bb:
                item["bbox"] = bb
            # ★ 좌표가 **다음 면**의 것일 수 있다 — 해설 그림이 면을 넘어간 문항이
            #   있다. 모델은 다음 면 이미지도 받으므로 그 면 좌표를 낼 수 있다.
            #   허용하는 값은 이 면과 다음 면뿐이다(그 이상은 모델의 헛디딤이다).
            if bb and page:
                try:
                    n = int(a.get("page") or 0)
                except (TypeError, ValueError):
                    n = 0
                if n == int(page) + 1:
                    item["page"] = n
        else:
            item["text"] = str(a.get("text") or "").strip()
        # ★ 빈 자산은 버린다. 모델이 `| 열1 | 열2 |` 같은 **빈 표 틀**을 내놓은 적이
        #   있다(실측) — 그대로 두면 화면에 유령 자산과 죽은 토큰이 생긴다.
        if not (item.get("md") or item.get("text") or (t == "figure")):
            seen[pre] -= 1
            continue
        # ★ 보기 뒤의 자료는 **해설**에 놓인다. `finalize` 가 이 값으로 갈라 쓴다
        #   (`f.get("placement") in ("해설","explanation")`).
        where = str((a or {}).get("placement") or "지문").strip()
        if where in ("해설", "explanation"):
            item["placement"] = "해설"
            expl.append(aid)
        else:
            order.append(aid)
        out[aid] = item
    if not out:
        return {}, "", ""
    tok = lambda ids: JOIN.join("{{" + i + "}}" for i in ids)
    # 모델이 넣은 토큰은 신뢰하지 않는다 — 우리가 매긴 순서로 다시 만든다.
    return out, tok(order), tok(expl)


def _clean(q: dict, size: tuple = (0, 0), page: int = 0) -> dict:
    """모델이 낸 문항 하나를 초안 형식으로 다듬는다.

    ★ 보기 앞에 원문자가 붙어 온 경우를 떼어 낸다. 지침으로 막았지만 모델이 지침을
      어길 때 그대로 저장하면 `①① 지역 데이터베이스…` 가 되어 파서가 헷갈린다.
    """
    ch = []
    for c in q.get("choices") or []:
        s = str(c).strip()
        if s[:1] in GLYPHS:
            s = s[1:].strip()
        ch.append(s)
    ans = str(q.get("answer") or "").strip()
    if ans and ans[0] not in GLYPHS:
        ans = ""                      # 원문자가 아니면 버린다 — 사람이 채운다
    out = {
        "question_no": int(q.get("question_no") or 0),
        # ★ 앱의 필드 이름이다 — `question`/`passage` 가 아니다. 화면(`ocr.js`)과
        #   확정(`finalize.py`) 둘 다 `stem`·`jimun` 만 읽는다. 이름이 어긋나면
        #   초안에 값이 들어 있어도 **발문 칸이 빈 채로 뜬다**(2026-08-18 실측).
        "stem": _detok(str(q.get("stem") or "")),
        "jimun": "",                      # 토큰은 `_assets` 가 정한다
        "explanation_raw": _detok(str(q.get("explanation") or "")),
        "choices": ch,
        "answer": ans[:1],
        "difficulty": str(q.get("difficulty") or "").strip(),
        "ocr_by": "claude",
    }
    # ★ 과목은 **문항번호로 정한다** — 모델에게 묻지 않는다. `book.json` 의
    #   subject_bounds 가 정답이고(SQLD 1~10 = 1과목, 11~50 = 2과목), 모델이 추측하면
    #   경계 문항에서 갈린다. 옛 확정본도 이 값을 갖고 있었다.
    if out["question_no"]:
        name, no = project.subject_for(out["question_no"])
        out["subject"], out["subject_no"] = name, no
    if out["difficulty"] not in ("하", "중", "상"):
        out.pop("difficulty")
    # 걸친 문항의 쪽 — **코드가 정한다.** 모델에게 쪽번호를 계산시키면 빠뜨린다
    # (실측: 합쳐 담고도 source_pages 를 비웠다). 불린 하나만 받는다.
    if q.get("spans_next") and page:
        out["source_pages"] = [int(page), int(page) + 1]
    assets, jimun_tok, expl_tok = _assets(q.get("assets") or [], size, page)
    if assets:
        out["assets"] = assets
    out["explanation"] = out.pop("explanation_raw", "")
    out["jimun"] = jimun_tok
    if expl_tok:
        # 해설 본문 뒤에 토큰을 붙인다 — 표가 설명 다음에 오는 인쇄 순서와 같다.
        out["explanation"] = (out["explanation"] + JOIN + expl_tok).strip()
    if ans:
        out["answer_index"] = GLYPHS.index(ans[0])
    note = str(q.get("note") or "").strip()
    if note:
        out["note"] = note
    return out


def read_one(src: str, page: int, *, model: str = "", effort: Optional[str] = None,
             on_activity: Optional[Callable[[str], None]] = None,
             overwrite: bool = False) -> dict:
    """페이지 하나를 판독해 초안으로 저장한다.

    `overwrite=False` 면 이미 문항이 든 초안은 건너뛴다 — 사람이 손본 초안을 모델이
    덮어쓰면 그 수정이 조용히 사라진다.
    """
    png = project.scan_png(src, int(page))
    if not os.path.isfile(png):
        raise FileNotFoundError(
            f"스캔 이미지가 없습니다: {png} — 먼저 [PDF 렌더] 를 누르세요.")

    cur = draft.load(src, int(page))
    if cur and (cur.get("questions") or []) and not overwrite:
        return {"src": src, "page": int(page), "skipped": True,
                "questions": len(cur["questions"]), "wrote": False}

    # 그림 좌표를 검증하려면 페이지 크기를 알아야 한다. PIL 은 헤더만 읽는다(가볍다).
    try:
        from PIL import Image
        with Image.open(png) as im:
            size = im.size
    except Exception:                                        # noqa: BLE001
        size = (0, 0)

    # ★ 다음 쪽도 준다 — 문항이 면 경계에서 잘린다(실측 18번: 발문 5쪽 · 보기 6쪽).
    #   마지막 면이면 주지 않는다.
    nxt = project.scan_png(src, int(page) + 1)
    nxt = nxt if os.path.isfile(nxt) else ""

    author = ClaudeAuthor(model=model, effort=effort,
                          cwd=os.path.dirname(png), on_activity=on_activity,
                          # 한 페이지는 이미지 한 장 읽고 끝이다. 헤맬 여지를 좁힌다.
                          max_turns=8,
                          # 스캔 PNG 두 장이 base64 로 실려 온다 — 기본 1MB 를 넘는다
                          max_buffer_size=32 * 1024 * 1024)
    got = author.structured(
        system=_system(),
        prompt=(f"다음 스캔 이미지를 판독하십시오.\n\n  {png}\n\n"
                + ("이어지는 면(참고용 — 걸친 문항을 완성할 때만 봅니다):" + chr(10)*2 + "  " + nxt + chr(10)*2 if nxt else "")
                + f"이 페이지는 `{src}` 의 {page}쪽입니다. "
                + (f"이미지 크기는 {size[0]}×{size[1]} 픽셀입니다. " if size[0] else "")
                + "Read 로 이미지를 열어 보고, 그 안에 실제로 인쇄된 것만 담으십시오."),
        schema=SCHEMA)

    d = draft.load_or_skeleton(src, int(page))
    qs = [_clean(q, size, int(page)) for q in (got.get("questions") or [])]
    qs = [q for q in qs if q["stem"] and q["question_no"]]
    d["questions"] = sorted(qs, key=lambda q: q["question_no"])
    d["ocr_text"] = str(got.get("ocr_text") or "")
    d["answer_key_line"] = str(got.get("answer_key_line") or "")
    d["notes"] = str(got.get("notes") or "")
    # 회차는 모델이 본 것이 있을 때만 덮는다 — 페이지 지도(page_map)가 이미 채워
    # 두었으면 그것이 더 믿을 만하다(사람이 회차를 판독해 둔 값이다).
    if not d.get("round") and got.get("round"):
        d["round"] = int(got["round"])
        d["round_label"] = str(got.get("round_label") or "")

    # ★ 회차가 비면 **앞 페이지에서 이어받는다.** 이 책은 회차 표기가 매 면에 찍혀
    #   있지 않아(실측 p.3) 모델이 null 을 낸다. 그러면 화면이 「회차와 문항번호를
    #   채우세요」로 확정을 막는다 — 사람이 페이지마다 손으로 넣을 일이 아니다.
    if not d.get("round"):
        d["round"], d["round_label"] = _carry_round(src, int(page), d["questions"])
    # 문항에도 찍는다. 확정(`finalize`)이 문항 단위로 `{RR}-{NN}.md` 를 쓴다.
    for q in d["questions"]:
        if d.get("round") and not q.get("round"):
            q["round"] = d["round"]
            if d.get("round_label"):
                q["round_label"] = d["round_label"]

    # ★ **문항이 0개인 면도 초안을 남긴다.** 앞 문항의 뒷부분만 있는 면이 그렇다.
    #
    #   지우는 쪽도 검토했다(2026-08-18). 안 지우는 이유가 셋:
    #     1. 지우면 「아직 안 읽은 면」과 「읽었는데 문항이 없는 면」을 **구별할 수 없다.**
    #        151장짜리 책에서 그 구별이 사라지면 진행 현황판을 믿을 수 없다.
    #     2. 건너뛰기 판정이 '초안 존재' 라서, 지우면 [스캔 판독] 이 그 면을 또 읽는다
    #        (걸친 면 9곳 × ~$0.2 이 한 바퀴마다 반복된다).
    #     3. 그 면의 `ocr_text` 가 앞 면 문항을 대조할 근거다(실측: p.48 의 ROLLUP 결과).
    #
    #   화면은 「이어짐」으로 표시한다 — 미완처럼 보이지 않게. 판정은 다른 페이지 문항의
    #   `source_pages` 가 이 쪽을 물고 있는가로 한다(`routes/ocr_routes.py` 의 overview).
    path, wrote = draft.save(src, int(page), d)
    return {"src": src, "page": int(page), "skipped": False, "wrote": wrote,
            "path": path, "questions": len(d["questions"]),
            "cost_usd": round(author.last_cost_usd, 4), "turns": author.last_turns,
            "notes": d["notes"]}


# ── 여러 페이지 — 잡으로 ─────────────────────────────────────────────────────
_LOCK = threading.Lock()

# ★ 줄줄이 실패할 때의 브레이크. 로그인이 끊기거나 한도에 걸리면 151장이 전부
#   같은 오류로 흘러간다 — 그 상태로 끝까지 돌면 시간만 태운다.
STALL_LIMIT = 3


def start(src: str, pages: list[int], *, model: str = "",
          effort: Optional[str] = None, overwrite: bool = False) -> dict:
    """페이지 목록을 판독하는 잡을 띄운다. 동시에 하나만.

    ★ 왜 잡인가 — 실측 한 페이지 43초다. 151장이면 두 시간에 가깝다. 요청-응답으로
      묶으면 브라우저가 먼저 끊긴다. 진행률·현재 페이지·취소가 다 필요하다.
    """
    from services.jobs import registry

    pages = [int(p) for p in pages]
    if not pages:
        raise ValueError("판독할 페이지가 없습니다.")
    if not _LOCK.acquire(blocking=False):
        raise RuntimeError("이미 판독이 돌고 있습니다 — 동시에 하나만 실행됩니다.")

    keys = [f"{src}:{p}" for p in pages]
    label = (f"판독 · {src} p.{pages[0]}~{pages[-1]} ({len(pages)}장)"
             if len(pages) > 1 else f"판독 · {src} p.{pages[0]}")
    job = registry.create("ocr", label, keys)
    job["options"] = {"src": src, "overwrite": overwrite,
                      "model": model, "effort": effort}

    def work(j: dict) -> None:
        try:
            _run(j, src, pages, model=model, effort=effort, overwrite=overwrite)
        finally:
            _LOCK.release()

    registry.spawn(job, work)
    return job


def _run(job: dict, src: str, pages: list[int], *, model: str,
         effort: Optional[str], overwrite: bool) -> None:
    from services.jobs import registry

    total_q = 0
    cost = 0.0
    fails = 0
    for p in pages:
        if job.get("cancel_requested"):
            registry.log(job, "[취소] 사람이 멈췄습니다.", force=True)
            break
        key = f"{src}:{p}"
        registry.item(job, key, status="running")
        job["current"] = f"{src} p.{p}"
        try:
            r = read_one(src, p, model=model, effort=effort, overwrite=overwrite,
                         on_activity=lambda s, _p=p: registry.log(job, f"  p.{_p} {s}"))
        except Exception as e:                                   # noqa: BLE001
            fails += 1
            registry.item(job, key, status="error", error=f"{type(e).__name__}: {e}")
            registry.log(job, f"[실패] p.{p} — {e}", force=True)
            if fails >= STALL_LIMIT:
                registry.log(job, f"[중단] {STALL_LIMIT}장 연속 실패 — 남은 페이지를 "
                                  "건너뜁니다. 로그인·한도를 확인하세요.", force=True)
                registry.finish(job, "error", error=f"{fails}장 연속 실패")
                return
            continue
        fails = 0
        total_q += r["questions"]
        cost += r.get("cost_usd") or 0.0
        job["done_count"] = job.get("done_count", 0) + 1
        if r["skipped"]:
            registry.item(job, key, status="done", output="건너뜀(이미 판독됨)")
            registry.log(job, f"  p.{p} 건너뜀 — 이미 {r['questions']}문항", force=True)
            continue
        registry.item(job, key, status="done",
                     output=f"{r['questions']}문항", seconds=None)
        registry.log(job, f"[판독] p.{p} → {r['questions']}문항 "
                          f"(${r.get('cost_usd', 0):.2f})", force=True)
        if r.get("notes"):
            registry.log(job, f"      메모: {r['notes'][:160]}")

    registry.log(job, f"[완료] {job.get('done_count', 0)}장 · {total_q}문항 · "
                      f"${cost:.2f}", force=True)
    # ★ `finish()` 에 넘겨야 한다. job["result"] 에 미리 넣어 두면 finish 가 그 자리를
    #   None 으로 덮는다(기본 인자) — 실측으로 result 가 비어서 잡았다.
    registry.finish(job, "done", result={
        "questions": total_q, "cost_usd": round(cost, 2),
        "pages": job.get("done_count", 0)})


def stamp_rounds(src: str, *, dry: bool = True) -> dict:
    """회차가 빈 초안에 **회차를 채운다.** 경계는 문항번호가 1로 리셋되는 자리다.

    ★ 페이지 수로 나누면 안 된다. 실측(SQLD 1.pdf) 1회·2회는 20쪽인데 3회는 23쪽이다 —
      해설 분량에 따라 회차마다 쪽수가 다르다. 20쪽으로 끊으면 3회 뒤가 통째로 밀린다.

    ★ 모델이 이미 붙인 회차는 **덮지 않는다.** 페이지에 회차 표기가 인쇄돼 있어 읽어
      낸 값이라 더 믿을 만하다. 실측에서 그 값들은 번호 리셋 경계와 전부 일치했다.

    ★ 판독이 빠진 페이지(실패·미판독)가 중간에 있어도 번호는 이어지므로 경계 판정이
      깨지지 않는다 — 리셋은 '앞 페이지의 마지막 번호보다 작아지는' 자리다.
    """
    pages = [(p, draft.load(src, p) or {}) for p in project.list_pages(src)]
    pages = [(p, d) for p, d in pages if (d.get("questions") or [])]
    cur = 0
    prev_max = 0
    plan, wrote = [], 0
    for p, d in pages:
        nos = sorted(q["question_no"] for q in d["questions"])
        if nos[0] <= prev_max:            # 번호가 되돌아갔다 → 새 회차
            cur += 1
        elif cur == 0:
            cur = 1
        prev_max = nos[-1]
        have = d.get("round")
        if have:
            cur = int(have)               # 인쇄된 회차를 기준으로 되맞춘다
            continue
        plan.append({"page": p, "round": cur, "q": f"{nos[0]}~{nos[-1]}"})
        if not dry:
            d["round"] = cur
            d.setdefault("round_label", project.round_label(cur) or "")
            draft.save(src, p, d)
            wrote += 1
    return {"src": src, "filled": plan, "count": len(plan), "wrote": wrote, "dry": dry}
