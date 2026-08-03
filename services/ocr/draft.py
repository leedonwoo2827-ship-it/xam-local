"""페이지 초안 — `data/ocr_draft/<src>_pNNN.json` 읽기·쓰기.

초안 하나 = 스캔 페이지 하나. 그 안에 그 페이지의 문제 여러 개가 들어 있다.

    {"src": "bdae1", "page": 1, "round": 1, "round_label": "제1회 실전모의고사",
     "ocr_text": "…페이지 판독 원문…", "answer_key_line": "정답 01③ 02④ …",
     "questions": [{question_no, subject_no, stem, jimun, choices[4], answer,
                    difficulty, explanation, assets{}, verified}, …]}

★ 이 폴더는 **Claude Code 창과 이 앱이 같이 쓴다.** 판독은 그 창이 하고 검수는 앱이
  한다. 그래서 원본 도구의 `write_text` 직접 쓰기를 원자적 쓰기 + `.bak` 으로 바꿨다 —
  앱이 저장하는 순간에 창이 같은 파일을 다시 쓰고 있어도 반쪽 파일이 남지 않는다.
"""
from __future__ import annotations

import json
import os
import re

from core.atomic_io import atomic_write_text, backup_sibling
from services.book import jsonio
from services.ocr import project

_NAME_RE = re.compile(r"^(?P<src>.+)_p(?P<page>\d{3,})\.json$")


def path_of(src: str, page: int) -> str:
    return os.path.join(project.draft_dir(), f"{src}_p{int(page):03d}.json")


def parse_name(name: str) -> tuple[str, int] | None:
    m = _NAME_RE.match(name)
    return (m.group("src"), int(m.group("page"))) if m else None


def load(src: str, page: int) -> dict | None:
    p = path_of(src, page)
    if not os.path.isfile(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def skeleton(src: str, page: int) -> dict:
    """초안이 아직 없는 페이지의 빈 틀. page_map 이 있으면 회차를 미리 채운다."""
    pm = project.page_map().get(f"{src}:{page}", {})
    return {
        "src": src,
        "page": int(page),
        "round": pm.get("round"),
        "round_label": pm.get("round_label"),
        "ocr_text": "",
        "answer_key_line": "",
        "questions": [],
        "notes": "",
    }


def load_or_skeleton(src: str, page: int) -> dict:
    return load(src, page) or skeleton(src, page)


def save(src: str, page: int, data: dict) -> tuple[str, bool]:
    """초안을 원자적으로 쓴다. `(경로, 실제로 썼는가)`.

    서식은 그 파일에서 되맞춘다(없으면 indent=2·LF).

    ★ 내용이 같으면 쓰지 않는다. 이 창(Claude Code)과 앱이 같은 폴더를 쓰기 때문에,
      아무것도 안 바뀐 저장이 mtime 을 흔들고 `.bak` 을 쌓으면 "무엇이 사람의 수정
      이었는지" 를 나중에 분간할 수 없다. 이 저장소의 다른 쓰기와 같은 규칙이다.
    """
    p = path_of(src, page)
    data = dict(data)
    data["src"] = src
    data["page"] = int(page)
    text = jsonio.render(p, data)
    if os.path.isfile(p):
        with open(p, encoding="utf-8", newline="") as f:
            if f.read() == text:
                return p, False
    backup_sibling(p)
    atomic_write_text(p, text)
    return p, True


def all_drafts(src: str | None = None) -> list[tuple[str, int]]:
    """(src, page) 목록 — 디스크를 센다. ★ 캐시하지 않는다.

    Claude Code 창에서 새 초안을 만들면 앱을 다시 띄우지 않고 패널만 열어도
    나타나야 한다.
    """
    d = project.draft_dir()
    if not os.path.isdir(d):
        return []
    out = []
    for f in sorted(os.listdir(d)):
        got = parse_name(f)
        if got and (src is None or got[0] == src):
            out.append(got)
    return out


def load_answers(src: str | None = None, round_no: int | None = None) -> list[dict]:
    """`data/answers/<src>_rNN.json` — 분리형 교재의 회차별 정답·해설."""
    d = project.answers_dir()
    if not os.path.isdir(d):
        return []
    out = []
    for f in sorted(os.listdir(d)):
        if not f.endswith(".json"):
            continue
        try:
            with open(os.path.join(d, f), encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(doc, dict):
            continue
        if src and str(doc.get("src")) != src:
            continue
        if round_no and int(doc.get("round") or 0) != int(round_no):
            continue
        doc["_file"] = f
        out.append(doc)
    return out
