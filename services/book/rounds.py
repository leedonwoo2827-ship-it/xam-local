"""_rounds/mNN.json — 집필 원천 읽기·쓰기.

이 파일은 도구 #1/#2 의 입력이기도 하다. 그래서 **스키마에 새 키를 추가하지
않는다** — has_sql / has_table 을 여기 넣고 싶은 유혹이 있지만, 그러면 우리가
만든 키를 저쪽 파이프라인이 모르는 상태가 된다.

회차별 RLock 안에서 읽기→수정→쓰기를 한다. BOOK 은 외부에서 다시 동기화될 수
있는 트리라, 락만으로는 부족하고 etag 대조가 함께 필요하다(store.py).
"""
from __future__ import annotations

import json
import os
import threading
from typing import Any

from core.atomic_io import atomic_write_json, backup_sibling
from services.book import paths

# 회차 단위 락. 한 회차의 80문항은 파일 하나에 들어 있어서, 두 요청이 같은
# 회차를 동시에 읽기-수정-쓰기 하면 나중 것이 앞 것을 통째로 되돌린다.
_LOCKS: dict[str, threading.RLock] = {}      # lock_for() 가 필요할 때 만든다
_LOCKS_GUARD = threading.Lock()

# 회차 메타 키 — questions 를 뺀 나머지. 저장할 때 이 순서를 유지한다.
META_KEYS = (
    "round_code", "round", "round_label", "subject_default", "theme",
    "voice", "speed", "countdown_seconds", "gap_seconds", "ai_reading",
)


def lock_for(round_code: str) -> threading.RLock:
    with _LOCKS_GUARD:
        if round_code not in _LOCKS:
            _LOCKS[round_code] = threading.RLock()
        return _LOCKS[round_code]


def load(round_code: str) -> dict[str, Any]:
    path = paths.rounds_json(round_code)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_all() -> dict[str, dict]:
    """회차 코드 → 회차 문서. 없는 회차는 건너뛴다(부분 동기화 상태 허용)."""
    out = {}
    for rc in paths.round_codes():
        if os.path.isfile(paths.rounds_json(rc)):
            out[rc] = load(rc)
    return out


def meta_of(doc: dict) -> dict:
    """questions 를 뺀 회차 메타. md 렌더러가 round / round_label 을 여기서 얻는다."""
    return {k: doc[k] for k in META_KEYS if k in doc}


def question_of(doc: dict, question_no: int) -> dict | None:
    """question_no 로 찾는다. 인덱스로 찍지 않는다 — 결번이 있을 수 있다."""
    for q in doc.get("questions") or []:
        if int(q.get("question_no", -1)) == int(question_no):
            return q
    return None


def question_index(doc: dict, question_no: int) -> int:
    for i, q in enumerate(doc.get("questions") or []):
        if int(q.get("question_no", -1)) == int(question_no):
            return i
    return -1


def save(round_code: str, doc: dict) -> None:
    """원자적 쓰기 + .bak 형제.

    .bak 을 남기는 이유: 이 파일 하나에 80문항이 들어 있어서, 렌더러 버그로
    한 번 잘못 쓰면 회차 전체를 잃는다. 되돌릴 수단이 손에 있어야 한다.
    """
    path = paths.rounds_json(round_code)
    backup_sibling(path)
    # _rounds 는 우리가 만든 파일이 아니므로 원본 포맷(indent=2)을 따른다.
    atomic_write_json(path, doc, indent=2)


def all_questions() -> list[tuple[str, dict, dict]]:
    """[(round_code, round_meta, question), ...] — 회차·문항번호 순.

    사전점검·색인·검증이 전부 이 하나를 쓴다.
    """
    out = []
    for rc, doc in load_all().items():
        meta = meta_of(doc)
        qs = sorted(doc.get("questions") or [], key=lambda q: int(q.get("question_no", 0)))
        for q in qs:
            out.append((rc, meta, q))
    return out
