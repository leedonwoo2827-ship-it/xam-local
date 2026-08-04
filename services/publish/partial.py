"""problems.json 을 **부분만** 잘라 낸다 — 회차·번들·문항 단위 재임포트용.

★ 왜 되는가
  임포트는 **DELETE 를 하지 않는다.** `adm/exam_lib/problem.php:13` 이 그렇게 적어 두었다:
  "DELETE + INSERT 를 하지 않는다. 기존 행은 UPDATE 만 한다."
  upsert 축은 `UNIQUE (pd_id, pr_key)` 다. 그래서 JSON 에 없는 문항은 서버에 그대로 남는다.
  → 문항 하나를 고쳤으면 그 하나만 담아 올려도 된다.

★ 왜 필요한가
  전체 problems.json 은 720문항에 714KB 다. 오타 하나를 고쳐도 그 전체를 다시 올리고
  임포트가 720행을 훑는다. 리포트도 "갱신 1 · 변경없음 719" 로 나와서 **내가 고친 것이
  정말 들어갔는지 눈으로 확인하기 어렵다.**
  회차 하나면 80KB, 문항 하나면 1KB 다. 리포트가 "갱신 1" 만 찍으면 확인이 끝난다.

★ 무엇을 그대로 두는가
  `pd_id` · `rounds` · `subjects` 는 원본 그대로 싣는다. 임포트가 `ex_round` 를 이
  `rounds` 로 upsert 하므로 빼면 회차 라벨·문항수가 갱신되지 않는다.
  (회차 행도 UPDATE 만 하므로 전체를 실어도 해가 없다.)
"""
from __future__ import annotations

import json
import os
import re

from services.book import paths

_BUNDLE_RE = re.compile(r"^m(\d{1,2})-(\d{1,2})$")


def source_path() -> str:
    """빌드가 만든 전체 problems.json."""
    return paths.problems_json()


def load() -> dict:
    p = source_path()
    if not os.path.isfile(p):
        raise ValueError(f"problems.json 이 없습니다: {p} — 먼저 빌드하세요.")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def summary() -> dict:
    """무엇을 잘라낼 수 있는지 — 화면이 고르게 한다."""
    doc = load()
    probs = doc.get("problems") or []
    by_round: dict[int, int] = {}
    by_bundle: dict[str, int] = {}
    unreviewed = 0
    for p in probs:
        rd = p.get("rd_no")
        if isinstance(rd, int):
            by_round[rd] = by_round.get(rd, 0) + 1
        b = p.get("bundle") or ""
        if b:
            by_bundle[b] = by_bundle.get(b, 0) + 1
        if p.get("needs_review"):
            unreviewed += 1
    return {
        "path": source_path(),
        "bytes": os.path.getsize(source_path()),
        "total": len(probs),
        "pd_id": doc.get("pd_id"),
        "rounds": dict(sorted(by_round.items())),
        "bundles": dict(sorted(by_bundle.items())),
        "unreviewed": unreviewed,
    }


def _select(probs: list[dict], *, rounds: list[int] | None,
            bundles: list[str] | None, keys: list[str] | None) -> list[dict]:
    if keys:
        want = set(keys)
        return [p for p in probs if p.get("pr_key") in want]
    out = probs
    if rounds:
        rs = {int(r) for r in rounds}
        out = [p for p in out if p.get("rd_no") in rs]
    if bundles:
        bs = set(bundles)
        out = [p for p in out if (p.get("bundle") or "") in bs]
    return out


def write(*, rounds: list[int] | None = None, bundles: list[str] | None = None,
          keys: list[str] | None = None, label: str = "") -> dict:
    """고른 문항만 담은 JSON 을 `06/_partial/` 에 쓴다.

    셋 다 비면 오류다 — "전체" 를 여기서 다시 만들 이유가 없다(원본을 올리면 된다).
    """
    if not (rounds or bundles or keys):
        raise ValueError("회차·번들·문항 중 하나는 골라야 합니다. "
                         "전체를 올릴 거면 원본 problems.json 을 쓰세요.")
    doc = load()
    probs = doc.get("problems") or []
    picked = _select(probs, rounds=rounds, bundles=bundles, keys=keys)
    if not picked:
        raise ValueError("고른 조건에 맞는 문항이 없습니다. "
                         f"(회차={rounds} 번들={bundles} 문항={keys})")

    out = {k: v for k, v in doc.items() if k != "problems"}
    out["problems"] = picked
    # 무엇을 왜 잘랐는지 파일에 남긴다 — 나중에 이 파일만 보고도 알 수 있어야 한다.
    out["_partial"] = {
        "of": len(probs), "picked": len(picked),
        "rounds": rounds or [], "bundles": bundles or [], "keys": keys or [],
        "note": ("부분 임포트용. 임포트는 DELETE 를 하지 않으므로(problem.php:13) "
                 "여기 없는 문항은 서버에 그대로 남습니다."),
    }

    name = label or _auto_name(rounds, bundles, keys)
    d = os.path.join(paths.out_dir(), "_partial")
    os.makedirs(d, exist_ok=True)
    dest = os.path.join(d, f"problems.{name}.json")
    tmp = dest + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.replace(tmp, dest)
    return {
        "path": dest, "bytes": os.path.getsize(dest),
        "picked": len(picked), "of": len(probs),
        "expect": f"신규 0 · 갱신 {len(picked)} 이하 · 회차 {len(out.get('rounds') or [])}행",
        "keys": [p.get("pr_key") for p in picked[:12]],
    }


def _auto_name(rounds, bundles, keys) -> str:
    if keys:
        return "q-" + "_".join(str(k).replace("#", "-") for k in keys[:3]) \
               + ("_외" if len(keys) > 3 else "")
    if bundles:
        return "b-" + "_".join(bundles[:3]) + ("_외" if len(bundles) > 3 else "")
    return "r-" + "_".join(f"m{int(r):02d}" for r in (rounds or [])[:4])
