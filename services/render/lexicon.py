# -*- coding: utf-8 -*-
"""용어 사전 — `vendor/chodangi/config/pronunciation_map.yaml` 을 앱에서 고친다.

**왜 앱에 붙이나.** 이 파일이 발음 고침의 **1차 자리**다. 한 줄 넣으면 72번들 전부에
걸리고 자막은 원문을 유지한다(엔진이 합성 직전에만 치환한다). 씬마다 손으로 고치는
것보다 훨씬 싸다 — 그런데 지금까지 앱에 입구가 없어서 파일을 직접 열어야 했다.

★ **헤더 주석을 보존한다.** 파일 머리에 동작 규칙이 적혀 있다(단어 경계·자막 미적용
  같은 것들). 통째로 다시 쓰면서 그것을 날리면 다음 사람이 규칙을 모른다.

★ 엔진은 이 파일을 **핫리로드**한다. 저장하면 다음 합성부터 바로 걸린다 —
  서버를 다시 띄울 필요가 없다.

★ 사전에 **없는** 대문자 약어는 엔진이 낱자로 음역한다(`spell_unknown_acronyms`).
  `MAE`→「엠에이이」처럼 맞는 것도 있지만 `CRISP`→「씨알아이에스피」처럼 틀리는 것도
  있다. `candidates()` 가 낭독문을 훑어 그 목록을 빈도와 함께 낸다 — 빈 화면을 주고
  "알아서 채우세요" 하지 않으려는 것이다.
"""
from __future__ import annotations

import collections
import glob
import json
import os
import re

from core.atomic_io import CRLF, LF, atomic_write_text, file_newline
from core.constants import ENGINE_DIR
from services.book import paths

MAP_PATH = os.path.join(ENGINE_DIR, "config", "pronunciation_map.yaml")

# 엔진의 판정과 **같아야 한다** — `voicewright/pronunciation.py` 의 `_ACRONYM_RE`.
_ACRONYM_RE = re.compile(r"(?<![A-Za-z])[A-Z]{2,}(?![A-Za-z])")
_LETTER = {
    "A": "에이", "B": "비", "C": "씨", "D": "디", "E": "이", "F": "에프",
    "G": "지", "H": "에이치", "I": "아이", "J": "제이", "K": "케이", "L": "엘",
    "M": "엠", "N": "엔", "O": "오", "P": "피", "Q": "큐", "R": "알",
    "S": "에스", "T": "티", "U": "유", "V": "브이", "W": "더블유",
    "X": "엑스", "Y": "와이", "Z": "제트",
}

_DEFAULT_HEADER = """# voicewright 발음 사전
#
# 합성 직전에 텍스트의 약자·외래어를 한국어 발음으로 자동 치환합니다.
#
#   - 단어 경계 매칭 — 앞뒤에 라틴 글자가 붙지 않은 것만 잡는다
#   - SRT 자막에는 적용되지 않음 (자막에는 항상 원본 텍스트가 들어감)
#   - 새 항목 추가 후엔 즉시 반영 (서버 재시작 불필요)
"""


def spelled(word: str) -> str:
    """사전에 없을 때 엔진이 내는 소리 — 낱자 음역."""
    return "".join(_LETTER.get(c, c) for c in word)


def _split(raw: str) -> tuple[str, dict]:
    """(헤더 주석, rules). `rules:` 첫 줄을 경계로 가른다."""
    import yaml
    lines = raw.splitlines(keepends=True)
    idx = next((i for i, ln in enumerate(lines) if ln.lstrip().startswith("rules:")), None)
    header = ("".join(lines[:idx]).rstrip() + "\n") if idx is not None else ""
    if not header.strip():
        header = _DEFAULT_HEADER
    try:
        rules = (yaml.safe_load(raw) or {}).get("rules") or {}
    except Exception:                     # noqa: BLE001 — 깨진 파일은 빈 dict 로 읽고 알린다
        return header, {}
    return header, {str(k): str(v) for k, v in rules.items()}


def read() -> dict:
    if not os.path.isfile(MAP_PATH):
        return {"exists": False, "path": MAP_PATH, "rules": {}, "count": 0}
    raw = open(MAP_PATH, encoding="utf-8").read()
    header, rules = _split(raw)
    ok = bool(rules) or "rules:" not in raw
    return {"exists": True, "path": MAP_PATH, "rules": rules, "count": len(rules),
            "header_lines": len(header.splitlines()),
            "error": "" if ok else "rules 를 읽지 못했습니다 — YAML 이 깨졌는지 보세요."}


def _write(header: str, rules: dict) -> None:
    """키 정렬 순서로 다시 쓴다. 헤더는 그대로 얹는다.

    ★ 원자적으로 쓴다 — 이 파일이 깨지면 **전 품목의 발음이 통째로 사라진다**
      (엔진은 로드 실패 시 규칙 0개로 조용히 계속 돈다).
    """
    def q(s: str) -> str:
        s = str(s)
        # YAML 이 특수하게 읽는 첫 글자·구두점이 있으면 따옴표로 감싼다
        return json.dumps(s, ensure_ascii=False) if re.search(r"^[\s#&*!|>%@`\[\]{}-]|[:#]", s) else s

    body = "".join(f"  {q(k)}: {q(rules[k])}\n" for k in sorted(rules))
    text = header.rstrip("\n") + "\n\nrules:\n" + body
    # ★ 개행은 **그 파일이 쓰던 것을 그대로** 쓴다. 이 PC 의 이 파일은 CRLF 이고
    #   `core.autocrlf=true` 라, LF 로 내려쓰면 내용이 같아도 git 이 통째로
    #   "변경됨" 으로 본다(실측 — 사전을 안 고쳤는데 M 으로 떴다).
    #   개행을 정하는 것은 호출자의 일이다(`atomic_write_text` 는 문자열 그대로 쓴다).
    nl = file_newline(MAP_PATH) or CRLF
    atomic_write_text(MAP_PATH, text.replace("\n", nl) if nl != LF else text)


def save(key: str, value: str) -> dict:
    k, v = (key or "").strip(), (value or "").strip()
    if not k:
        raise ValueError("용어가 비어 있습니다.")
    if not v:
        raise ValueError("읽는 소리가 비어 있습니다 — 지우려면 [빼기] 를 쓰세요.")
    raw = open(MAP_PATH, encoding="utf-8").read() if os.path.isfile(MAP_PATH) else ""
    header, rules = _split(raw)
    if raw and not rules:
        raise ValueError("사전을 읽지 못했습니다 — 덮어쓰지 않았습니다. YAML 을 확인하세요.")
    was = rules.get(k)
    rules[k] = v
    _write(header, rules)
    return {"key": k, "value": v, "was": was, "count": len(rules)}


def remove(key: str) -> dict:
    k = (key or "").strip()
    raw = open(MAP_PATH, encoding="utf-8").read() if os.path.isfile(MAP_PATH) else ""
    header, rules = _split(raw)
    if k not in rules:
        raise ValueError(f"사전에 없습니다: {k}")
    was = rules.pop(k)
    _write(header, rules)
    return {"key": k, "was": was, "removed": True, "count": len(rules)}


def candidates(prefix: str = "") -> list[dict]:
    """낭독문에 있는데 **사전에 없는** 대문자 약어. 빈도가 큰 것부터.

    `prefix` 로 회차를 좁힌다(`m01` → 1회 8번들).
    """
    rules = read()["rules"]
    hits: collections.Counter[str] = collections.Counter()
    where: dict[str, str] = {}
    pat = os.path.join(paths.book_dir(), "05", (prefix or "") + "*",
                       "script", "*_script.json")
    for sp in sorted(glob.glob(pat)):
        try:
            doc = json.load(open(sp, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        bundle = os.path.basename(os.path.dirname(os.path.dirname(sp)))
        for s in doc.get("scenes") or []:
            # ★ **자막**(narration)을 본다. 발음(narration_text)에는 이미 손이 닿아
            #   있어서, 고친 것을 다시 후보로 올리게 된다.
            t = s.get("narration") or ""
            for m in _ACRONYM_RE.finditer(t):
                w = m.group(0)
                if w in rules:
                    continue
                hits[w] += 1
                where.setdefault(w, f"{bundle} 씬{s.get('scene')} … "
                                    + t[max(0, m.start() - 20):m.start() + len(w) + 12])
    return [{"term": w, "count": n, "now": spelled(w), "where": where[w]}
            for w, n in hits.most_common()]
