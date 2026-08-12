# -*- coding: utf-8 -*-
"""집필 출력 스키마 — `_rounds/mNN.json` 의 문항 모양.

★ 발명한 것이 아니다. `D:\\00work\\ocr-output-260730\\_rounds\\m01.json` 의 80문항을
  실측해 키 출현수를 세어 뽑았다(2026-08-10):

    80/80 : question_no subject subject_no difficulty tags derived_from
            question passage choices answer_index explanation explanation_speech
    26/80 : assets          ← 그림 문항만
     2/80 : table           ← 표 지문 문항만

  ★ 처음 쓴 탐침은 `number` 를 썼다 — **틀린 키다.** 실제는 `question_no` 다.
    확인하지 않고 갔으면 `build.py` 가 그 문항을 조용히 건너뛰었을 것이다.
    (`vendor/exambook/build.py` 는 우리 코드가 아니므로 우리가 키를 정할 수 없다.)

★ `additionalProperties: false` 를 반드시 건다. 모델이 그럴듯한 여분 키
  (`answer` · `subject_name` · `id`)를 붙이면 `build.py` 는 무시하고 지나가고,
  사람은 웹에 올라간 뒤에야 뭔가 빠진 것을 안다.

★ `passage` 는 80/80 에 있지만 **없는 문항은 빈 문자열**이다. required 에 넣고
  빈 문자열을 허용한다 — 키를 빼면 `05/lesson` 규약(지문 없으면 키 자체를 뺀다)과
  섞여서 어느 쪽이 맞는지 헷갈린다. `_rounds` 는 항상 넣는 쪽이다.
"""
from __future__ import annotations

from typing import Any, Dict, List

# 4지선다 고정. 이 책은 전 문항 4지선다다(프롬프트 문서 명시).
N_CHOICES = 4

# 과목 문자열 — **한 글자도 바꾸면 안 된다.** 요약노트 <h1>N과목 · 이름</h1> 과
# 일치해야 성적표의 과목별 링크가 붙는다(프롬프트 문서 33-34행).
SUBJECTS: Dict[int, str] = {
    1: "빅데이터 분석 기획",
    2: "빅데이터 탐색",
    3: "빅데이터 모델링",
    4: "빅데이터 결과 해석",
}

DIFFICULTIES = ["상", "중", "하"]


def _item_schema(subject_nos: List[int], numbers: List[int]) -> Dict[str, Any]:
    """문항 1개 스키마. 파트마다 번호·과목을 **enum 으로 못박는다.**

    왜 enum 인가: 파트 3(21~30번)을 요청했는데 모델이 1~10번을 쓰면 반입 때
    이미 있는 문항을 덮는다. 스키마에서 막으면 그 실패가 애초에 불가능해진다.
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["question_no", "subject", "subject_no", "difficulty", "tags",
                     "derived_from", "question", "passage", "choices",
                     "answer_index", "explanation", "explanation_speech"],
        "properties": {
            "question_no": {"type": "integer", "enum": numbers},
            "subject_no": {"type": "integer", "enum": subject_nos},
            # 과목명도 enum — subject_no 와 어긋나는 조합을 스키마가 막지는 못하므로
            # draft.py 가 교차 검증한다. 그래도 오타는 여기서 걸린다.
            "subject": {"type": "string", "enum": [SUBJECTS[n] for n in subject_nos]},
            "difficulty": {"type": "string", "enum": DIFFICULTIES},
            "tags": {"type": "array", "items": {"type": "string"},
                     # 프롬프트 문서는 2~4개다. 실측에서 모델이 6개를 냈다 —
                     # 규약을 말로만 적으면 넘긴다. 스키마로 막는다.
                     "minItems": 2, "maxItems": 4},
            # ★ 빈 문자열을 허용한다. `mode="exam"`(실제 시험 기준)에서는 기출 파생
            #   관계가 없으므로 넣을 값이 없다. `minLength:1` 을 걸면 모델이 없는 기출
            #   id 를 지어낸다 — 추적용 필드에 거짓이 들어가는 것이 비는 것보다 나쁘다.
            "derived_from": {"type": "string"},
            "question": {"type": "string", "minLength": 10},
            # 지문 없는 문항은 빈 문자열. 위 머리말 참조.
            "passage": {"type": "string"},
            "choices": {"type": "array", "items": {"type": "string", "minLength": 1},
                        "minItems": N_CHOICES, "maxItems": N_CHOICES},
            # 0-based. `build.py` 가 circled(answer_index) 로 ①②③④ 를 만든다.
            "answer_index": {"type": "integer", "minimum": 0,
                             "maximum": N_CHOICES - 1},
            # ★ 양쪽 다 본다. 실측 3회로 확인한 것:
            #     기준(검증된 m01)      화면 166자 · 낭독 356자 → 편당 15분
            #     1차: 비율만 줬다      화면 919자 · 낭독 1552자 → 편당 47분
            #     2차: 상한만 걸었다    화면 147자 · 낭독  272자 → 편당 8.3분
            #     3차: 하한도 걸었다    낭독 307~339자 11건(m08-p4) → **하한에 붙었다**
            #   모델은 제시 구간의 아래쪽에 붙는다. 그런데 3차가 보여 준 것은 하한을
            #   올려도 그 **바로 위**에 붙는다는 것이다 — 목표는 350~450 인데 결과가
            #   307~339 였다. 하한은 목표를 만들지 않고 바닥을 만든다. 목표를 잡는 것은
            #   프롬프트다(spec.py "■ ★ 분량").
            #
            # ★ 그래서 하한은 **outlier 만 막는 값으로 내렸다**(140→100 · 300→240).
            #   2026-08-12, m09-p1 이 이 하한 때문에 무한루프에 빠졌다:
            #     ① 20문항을 다 써서 냈다(45,024토큰)
            #     ② 17번째 explanation 이 140자에 몇 자 미달 → 스키마가 **20문항 전부**
            #        를 반려("must NOT have fewer than 140 characters")
            #     ③ 재생성이 출력 상한(64,000토큰)을 넘겨 잘렸다
            #     ④ 잘린 응답이 다음 시도의 컨텍스트에 남아 **또** 잘렸다 — 세 번이
            #        정확히 64,000 에서 멈췄다. 5시간 · 237,000토큰 · 0문항.
            #   하한을 중앙값 근처에 두면 문항 20개 중 하나는 반드시 밑으로 내려간다
            #   (화면 중앙값 166 vs 하한 140). 한 문항의 미달이 20문항 재생성을 부르는
            #   구조 자체가 틀렸다. 미달은 draft.py `_validate` 가 경고로 남긴다 —
            #   사람이 보고 판단할 일이고, 스키마는 모양만 본다(provider.py 계층 규약).
            #   ★ 재생성이 무한히 돌지 않는 것은 provider.py `_abort_reason` 이 막는다.
            #     여기 하한을 내리는 것은 **애초에 안 걸리게** 하는 것이고, 그쪽은
            #     걸렸을 때 **끊는** 것이다. 둘 다 있어야 한다.
            #
            # ★ 상한은 남긴다. 20문항을 한 응답에 담는 근거이고(draft.py:42), 중앙값
            #   에서 멀어(166 vs 320) 걸릴 일이 없다.
            "explanation": {"type": "string", "minLength": 100, "maxLength": 320},
            "explanation_speech": {"type": "string", "minLength": 240, "maxLength": 520},
            # ── 그림 ────────────────────────────────────────────────────────
            # ★ 처음에 이 필드를 **빼먹었다.** 그대로 돌리면 그림이 0개인 문제집이
            #   나온다 — 기존 책은 `02/assets` 에 SVG 246개, m01 80문항 중 26문항이
            #   그림을 가진다. 회귀다.
            #
            # 형식은 실측이다(`_rounds/m01.json`): `[{"name": "...", "svg": "<svg …>"}]`
            #   name : 파일명이 된다(`02/assets/{name}.svg`). id 접두를 붙인다 —
            #          `m01-02-dikw` 처럼. 그래야 회차를 지워도 남의 그림을 안 지운다.
            #   svg  : **인라인 SVG 문자열.** `05/lesson` 에서는 파일명 배열로 바뀌지만
            #          `_rounds` 는 인라인이다(집필 규약 문서 명시).
            #
            # ★ 세로 예산을 먹는다. 슬라이드 실측: 그림이 카드 예산 652px 중 273px(42%)
            #   을 쓰고 남는 것으로 발문 2줄 + 보기 4개가 딱 찬다. 그래서 **모든 문항에
            #   넣지 않는다** — 프롬프트가 "그림이 이해를 돕는 문항에만" 이라고 지시하고
            #   기존 비율(26/80 ≈ 3분의 1)을 목표로 준다.
            "assets": {
                "type": "array",
                "maxItems": 2,          # 한 문항에 3개 이상은 슬라이드에 안 들어간다
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["name", "svg"],
                    "properties": {
                        "name": {"type": "string", "minLength": 3, "maxLength": 60},
                        # 상한: 인라인 SVG 가 너무 크면 응답 토큰을 다 먹고 문항이 잘린다.
                        "svg": {"type": "string", "minLength": 40, "maxLength": 4000},
                    },
                },
            },
        },
    }


def part_schema(subject_nos: List[int], numbers: List[int]) -> Dict[str, Any]:
    """파트 1개(보통 10문항)의 응답 스키마.

    ★ 문항 배열을 `items` 한 겹으로 감싼다. 최상위를 배열로 두면 SDK 의
      `output_format` 이 object 를 요구해 거절한다.
    ★ `minItems == maxItems == len(numbers)` — 개수 부족을 스키마가 막는다.
      막지 않으면 10개를 요청해 7개만 와도 `subtype=="success"` 다.
    """
    n = len(numbers)
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["items"],
        "properties": {
            "items": {
                "type": "array",
                "minItems": n, "maxItems": n,
                "items": _item_schema(subject_nos, numbers),
            }
        },
    }


def subject_no_for(question_no: int) -> int:
    """문항번호 → 과목번호. 1~20=1과목, 21~40=2과목, 41~60=3과목, 61~80=4과목.

    ★ 내용이 아니라 **번호에서** 나온다. `pr_key` 가 번호에서 파생되는 것과 같은
      이유다 — 다시 만들어도 같은 값이 나와야 임포트가 UPSERT 로 맞아 들어간다.
    """
    if not 1 <= question_no <= 80:
        raise ValueError(f"문항번호가 1~80 밖입니다: {question_no}")
    return (question_no - 1) // 20 + 1
