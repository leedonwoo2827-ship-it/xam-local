# -*- coding: utf-8 -*-
"""자사 문제집 안의 **중복 문항 검출.** 반입을 막는 게이트다.

★ 요구(2026-08-10): *"자사 회차 내는 물론 자사 문제집 내에서 동일 문제가 만들어지면
  안 됩니다."*

왜 프롬프트로는 부족한가 — 1,000제(20회차 × 50문항)를 **서로 볼 수 없는** 20~80회의
호출로 만든다. 호출 하나는 자기가 쓰는 20문항만 안다. "중복하지 마라" 고 적어도
다른 호출이 무엇을 썼는지 모르므로 새어 나온다. 그래서 두 겹으로 간다:

  ① 프롬프트 — 이미 쓴 개념(tags)을 넘겨 회피를 유도한다(`spec.part_prompt` 의 회차 차별화)
  ② **검출** — 이 파일. 새 문항을 **이미 있는 전부**와 비교해 걸린 것을 반입에서 막는다.
     ①이 실패해도 ②가 잡는다. ②가 보증이고 ①은 비용 절감이다.

★ 임베딩을 쓰지 않는다. 의존성 0 · 즉시 · 결정적이어야 하고(같은 입력에 같은 판정),
  우리가 잡아야 하는 것은 "의미가 비슷한 다른 문항" 이 아니라 **같은 문항**이다.
  자카드 유사도로 충분하고, 그 판정 근거를 사람에게 보여줄 수 있다(공통 토큰).
"""
from __future__ import annotations

import glob
import json
import os
import re
from typing import Any, Dict, Iterable, List, Tuple

# 판정 임계값 — 실측으로 조정할 값이다. 0.72 는 "발문 절반 이상이 같은 낱말" 수준이다.
DUP = 0.72          # 이 이상이면 중복으로 막는다
NEAR = 0.58         # 이 이상이면 경고만 (사람이 본다)

# 조사·기호를 떼고 낱말만 남긴다. 한국어라 형태소 분석 없이 어절 단위로 자른다 —
# "이상값으로" 와 "이상값은" 이 다른 토큰이 되지만, 그 둘이 같이 나오는 문항은
# 어차피 다른 어절도 많이 겹친다(자카드가 잡는다).
_STRIP = re.compile(r"[^\w가-힣]+")
# 어느 문항에나 나오는 말 — 유사도를 부풀린다
_STOP = {"다음", "중", "것은", "무엇인가", "옳은", "옳지", "않은", "가장", "모두",
         "고른", "설명", "대한", "다음중", "적절한", "관한", "경우", "때"}


def _tokens(item: Dict[str, Any]) -> frozenset:
    """발문 + 보기 + 지문을 한 자루로. 해설은 넣지 않는다 — 길어서 유사도를 눌러 버린다."""
    parts = [str(item.get("question") or ""), str(item.get("passage") or "")]
    parts += [str(c) for c in (item.get("choices") or [])]
    ws = _STRIP.sub(" ", " ".join(parts)).split()
    return frozenset(w for w in ws if len(w) > 1 and w not in _STOP)


def _sim(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _label(it: Dict[str, Any], where: str) -> str:
    return f"{where} {it.get('question_no')}번"


def existing(book_dir: str, *, skip_round: str = "") -> List[Tuple[str, Dict[str, Any]]]:
    """이미 있는 자사 문항 전부 — `_rounds/*.json`.

    `skip_round` 는 지금 다시 집필하는 회차다. 자기 자신과 비교하면 재집필이 전부
    중복으로 잡힌다(UPSERT 로 덮을 것이므로 중복이 아니다).
    """
    out: List[Tuple[str, Dict[str, Any]]] = []
    for p in sorted(glob.glob(os.path.join(book_dir, "_rounds", "m*.json"))):
        code = os.path.basename(p)[:-5]
        if skip_round and code == skip_round:
            continue
        try:
            with open(p, encoding="utf-8") as f:
                doc = json.load(f)
        except (OSError, ValueError):
            continue
        for q in doc.get("questions") or []:
            out.append((f"{int(code[1:])}회차", q))
    return out


def check(new_items: Iterable[Dict[str, Any]], *, book_dir: str,
          round_code: str = "", within_label: str = "이 회차") -> Dict[str, Any]:
    """새 문항을 ① 서로, ② 이미 있는 전부와 비교한다.

    돌려주는 것:
        dups  — 막아야 하는 것 (DUP 이상)
        nears — 사람이 볼 것 (NEAR ~ DUP)
    """
    items = list(new_items)
    sigs = [(_label(it, within_label), _tokens(it), it) for it in items]
    old = [(w, _tokens(q), q) for w, q in existing(book_dir, skip_round=round_code)]

    dups: List[Dict[str, Any]] = []
    nears: List[Dict[str, Any]] = []

    def add(a_label, b_label, score, shared):
        row = {"a": a_label, "b": b_label, "score": round(score, 3),
               "shared": sorted(shared)[:8]}
        (dups if score >= DUP else nears).append(row)

    # ① 새 문항끼리 — 같은 호출 안에서도 중복이 난다(20문항을 한 번에 쓰므로)
    for i in range(len(sigs)):
        for j in range(i + 1, len(sigs)):
            s = _sim(sigs[i][1], sigs[j][1])
            if s >= NEAR:
                add(sigs[i][0], sigs[j][0], s, sigs[i][1] & sigs[j][1])

    # ② 이미 있는 전부와 — **여기가 "문제집 내 중복" 을 막는 곳**
    for lab, sig, _ in sigs:
        for olab, osig, _o in old:
            s = _sim(sig, osig)
            if s >= NEAR:
                add(lab, f"{olab} {_o.get('question_no')}번", s, sig & osig)

    return {
        "checked": len(items),
        "against": len(old),
        "dups": sorted(dups, key=lambda r: -r["score"]),
        "nears": sorted(nears, key=lambda r: -r["score"])[:20],
        "threshold": {"dup": DUP, "near": NEAR},
    }


def problems(report: Dict[str, Any]) -> List[str]:
    """반입을 막는 문장. 사람이 읽고 무엇을 고칠지 알 수 있어야 한다."""
    out = []
    for r in report.get("dups") or []:
        out.append(f"중복 {int(r['score'] * 100)}% — {r['a']} ↔ {r['b']} "
                   f"(공통: {' '.join(r['shared'][:5])})")
    return out
