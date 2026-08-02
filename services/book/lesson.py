"""05/<bundle>/source/lesson_<bundle>.json — ★ 문제 본문이 실제로 웹에 가는 경로.

axexam 의 scripts/build_check.py 는 문제문·보기·해설·정답을 **이 파일에서만**
읽는다(`collect()`). 02/*.md 는 과목·난이도·태그·verified/reviewed/needs_review
만 공급한다(`exam_meta.py::_MD_ONLY`).

그래서 문항을 고칠 때 02/*.md 만 쓰면 다음 빌드가 낡은 05 본문을 다시 내보내고,
pr_hash 가 그대로여서 임포트가 '변경없음' 을 찍는다 — 수정이 웹에 전혀 반영되지
않는다. 이 모듈이 그 구멍을 막는다.

실측 형식 (05/m01-1/source/lesson_m01-1.json, 14275 bytes):
  · json indent=2, ensure_ascii=False, **끝에 개행 없음**, LF 전용
  · blocks[] 는 kind="section" 과 kind="problem" 이 섞여 있다
  · problem 블록 키 순서:
      kind number type question choices answer answer_index
      explanation explanation_speech difficulty tags [assets]
  · number 는 **전역 문항번호**(1~80)다. 번들 안 순번이 아니다
  · assets 는 **파일명 배열**(["m01-02-dmz.svg"]) — _rounds 의 인라인 SVG 가 아니다
  · subject / subject_no / derived_from 은 여기 **없다**(그래서 과목이 02 에서만 온다)
"""
from __future__ import annotations

import json
import os

from core.atomic_io import atomic_write_json, backup_sibling
from services.book import derive, paths

# problem 블록 키 순서 — 실측값. assets 는 있을 때만 맨 뒤에 붙는다.
BLOCK_ORDER = (
    "kind", "number", "type", "question", "choices", "answer", "answer_index",
    "explanation", "explanation_speech", "difficulty", "tags",
)


def load(bundle: str) -> dict:
    with open(paths.bundle_lesson(bundle), encoding="utf-8") as f:
        return json.load(f)


def problem_blocks(doc: dict) -> list[dict]:
    """kind=="problem" 인 블록만. build_check.collect() 와 같은 판정 규칙을 쓴다."""
    out = []
    for b in doc.get("blocks") or []:
        if b.get("kind") == "problem" or b.get("question"):
            out.append(b)
    return out


def block_index(doc: dict, question_no: int) -> int:
    """전역 문항번호로 blocks[] 안의 위치를 찾는다."""
    for i, b in enumerate(doc.get("blocks") or []):
        if (b.get("kind") == "problem" or b.get("question")) and \
                int(b.get("number", -1)) == int(question_no):
            return i
    return -1


def render_block(question: dict, previous: dict | None = None,
                 keep_speech: bool = False) -> dict:
    """_rounds 의 질문 → 05 lesson 의 problem 블록.

    previous 가 있으면 우리가 관리하지 않는 키(있다면)를 보존한다. 실측 형식에는
    그런 키가 없지만, 도구 #2 가 나중에 키를 늘렸을 때 조용히 지워 버리지 않도록
    안전판을 둔다.

    keep_speech: explanation_speech 를 디스크 값 그대로 둔다.
      ★ 실측 드리프트가 있다. m01-5(q42) · m02-5(q45) 두 문항은 lesson 쪽 낭독문이
        "…개발된 언어는 알이며…" 인데 _rounds 는 "…알(R)이며…" 다. TTS 가 "(R)" 을
        "괄호 알 괄호" 로 읽어 버리는 걸 누군가 lesson 에서 손으로 고쳐 둔 것이다.
        사용자가 낭독문을 건드리지 않았다면 그 손질을 되돌리지 않는다.
    """
    block = {
        "kind": "problem",
        "number": int(question["question_no"]),
        "type": (previous or {}).get("type") or "multiple_choice",
        "question": (question.get("question") or "").strip(),
        "choices": [(c or "").strip() for c in (question.get("choices") or [])],
        "answer": derive.answer_glyph(question["answer_index"]),
        "answer_index": int(question["answer_index"]),
        # ★ 05 lesson 의 explanation 은 인라인 그림 줄을 **뺀** 형태다(실측).
        #   그림 정보는 아래 assets 가 따로 들고 있어서 중복이기 때문이다.
        #   02/*.md 는 반대로 그림 줄을 품은 원문을 그대로 쓴다.
        "explanation": derive.strip_inline_figures(question.get("explanation") or ""),
        "explanation_speech": (question.get("explanation_speech") or "").strip(),
        "difficulty": question["difficulty"],
        "tags": list(question.get("tags") or []),
    }
    if keep_speech and previous and "explanation_speech" in previous:
        block["explanation_speech"] = previous["explanation_speech"]

    names = derive.asset_filenames(question)
    if names:
        block["assets"] = names

    # 우리가 모르는 키는 뒤에 붙여 보존한다.
    if previous:
        for k, v in previous.items():
            if k not in block and k != "assets":
                block[k] = v
    return block


def render(doc: dict, question: dict, keep_speech: bool = False) -> dict:
    """문서 사본에 문항 하나를 반영한다. 원본 dict 는 건드리지 않는다."""
    out = dict(doc)
    blocks = list(doc.get("blocks") or [])
    i = block_index(doc, int(question["question_no"]))
    if i < 0:
        raise ValueError(
            f"lesson 에 {question['question_no']}번 문항 블록이 없습니다. "
            f"번들과 문항 번호가 어긋났습니다."
        )
    blocks[i] = render_block(question, blocks[i], keep_speech=keep_speech)
    out["blocks"] = blocks
    return out


def speech_drift() -> list[dict]:
    """05 lesson 의 낭독문이 _rounds 와 다른 문항 목록.

    조용히 한쪽이 이기게 하지 않는다 — 어느 문항이 갈라져 있는지 화면에 보여주고,
    사용자가 낭독문을 실제로 고칠 때만 lesson 쪽을 덮어쓴다.
    """
    from services.book import rounds
    out = []
    by_round = rounds.load_all()
    for bundle in paths.all_bundles():
        parsed = paths.parse_bundle(bundle)
        if not parsed:
            continue
        doc_r = by_round.get(paths.round_code(parsed[0]))
        if not doc_r or not os.path.isfile(paths.bundle_lesson(bundle)):
            continue
        try:
            doc_l = load(bundle)
        except (OSError, json.JSONDecodeError):
            continue
        lo, hi = paths.bundle_range(bundle)
        for qno in range(lo, hi + 1):
            q = rounds.question_of(doc_r, qno)
            i = block_index(doc_l, qno)
            if q is None or i < 0:
                continue
            disk = doc_l["blocks"][i].get("explanation_speech") or ""
            src = (q.get("explanation_speech") or "").strip()
            if disk.strip() != src:
                out.append({
                    "id": paths.qid(parsed[0], qno),
                    "bundle": bundle,
                    "lesson": disk,
                    "rounds": src,
                })
    return out


def render_text(doc: dict) -> str:
    """실측 포맷 — indent=2, ensure_ascii=False, 끝 개행 없음."""
    return json.dumps(doc, ensure_ascii=False, indent=2)


def save(bundle: str, doc: dict) -> bool:
    """내용이 실제로 바뀐 경우에만 쓴다. 바뀌었으면 True."""
    path = paths.bundle_lesson(bundle)
    text = render_text(doc)
    if os.path.isfile(path):
        with open(path, encoding="utf-8", newline="") as f:
            if f.read() == text:
                return False
    backup_sibling(path)
    from core.atomic_io import atomic_write_text
    atomic_write_text(path, text)
    return True


def question_to_block_diff(bundle: str, question: dict) -> dict | None:
    """지금 디스크의 블록과 _rounds 의 질문이 어긋난 필드를 알려준다.

    드리프트 탐지용 — 사람이 lesson 을 직접 고쳤을 수도 있다.
    """
    try:
        doc = load(bundle)
    except (OSError, json.JSONDecodeError):
        return {"error": "lesson 파일을 읽을 수 없습니다."}
    i = block_index(doc, int(question["question_no"]))
    if i < 0:
        return {"error": f"{question['question_no']}번 블록이 없습니다."}
    cur = doc["blocks"][i]
    want = render_block(question, cur)
    diff = {}
    for k in ("question", "choices", "answer", "answer_index", "explanation",
              "explanation_speech", "difficulty", "tags", "assets"):
        if cur.get(k) != want.get(k):
            diff[k] = {"disk": cur.get(k), "rounds": want.get(k)}
    return diff or None
