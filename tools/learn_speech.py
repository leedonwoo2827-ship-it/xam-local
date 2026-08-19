# -*- coding: utf-8 -*-
"""사람이 고친 **발음대본을 읽어** 규칙으로 올릴 것을 뽑는다.

  python tools/learn_speech.py              전부
  python tools/learn_speech.py m01           1회만 (접두어로 고른다)
  python tools/learn_speech.py --verify      규칙이 손수정과 같은 결과를 내는지 검산

**왜 이 도구가 있나.** 자격증을 하나씩 내면서 **사람 수정을 줄이는** 것이 목표다.
1회를 손으로 고치고 나면 그 수정 안에 되풀이되는 것이 있다 — 그것을 규칙으로 올리면
다음 회차·다음 자격증(SQLD 등)은 고칠 것이 줄어든 상태로 시작한다.

읽는 것은 `05/<번들>/script/<번들>_speech.json` 의 `from`(자막 원문) → `text`(고친 발음)
쌍이다. 그래서 저장할 때 `from` 을 함께 남긴다(`services/render/speech.py`).

★ **2회 이상 되풀이되는 것만** 규칙 후보로 올린다. 한 번뿐인 것은 그 씬의 발음으로
  남겨 두는 것이 맞다 — 규칙은 전 품목에 퍼지므로 근거가 얇으면 그게 사고가 된다.

★ 규칙으로 올린 뒤에도 그 씬의 덮어쓰기를 **지우지 않는다.** `--verify` 로 규칙이 같은
  결과를 내는지 확인만 한다. 어긋나면 그것은 규칙의 버그다.
"""
from __future__ import annotations

import collections
import difflib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.speak import to_speech          # noqa: E402
from services.book import paths           # noqa: E402
from services.render import speech        # noqa: E402


def _pairs(prefix: str = "") -> list[tuple[str, int, str, str]]:
    """(번들, 씬, 자막원문, 고친발음) 목록."""
    out = []
    for b in paths.all_bundles():
        if prefix and not b.startswith(prefix):
            continue
        for si, e in sorted(speech.overrides(b).items()):
            src = (e.get("from") or "").strip()
            dst = (e.get("text") or "").strip()
            if src and dst and src != dst:
                out.append((b, si, src, dst))
    return out


# 갈래를 가르는 규칙. 위에서부터 먼저 맞는 것으로 센다.
_KIND = (
    ("숫자·기호", re.compile(r"[\d%]")),
    ("자모", re.compile(r"[ㄱ-ㅎ]")),
    ("영문", re.compile(r"[A-Za-z]")),
)


def _kind(before: str, after: str) -> str:
    """무엇이 사라졌는가로 갈래를 정한다 — 고침은 대개 '읽지 못하는 것'을 없애는 일이다."""
    gone = "".join(t[2:] for t in difflib.ndiff(before, after) if t.startswith("- "))
    for name, pat in _KIND:
        if pat.search(gone):
            return name
    if "(" in gone or ")" in gone:
        return "괄호"
    return "문장"


def _words(before: str, after: str) -> list[tuple[str, str]]:
    """바뀐 **낱말 덩이**만 뽑는다. 되풀이를 세려면 문장이 아니라 덩이여야 한다."""
    a, b = before.split(), after.split()
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
        if tag == "equal":
            continue
        out.append((" ".join(a[i1:i2]), " ".join(b[j1:j2])))
    return out


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    verify = "--verify" in argv
    prefix = args[0] if args else ""

    pairs = _pairs(prefix)
    if not pairs:
        where = f"{prefix}* " if prefix else ""
        print(f"고친 발음이 없습니다 ({where}05/*/script/*_speech.json).")
        print("영상 화면에서 발음을 고쳐 [발음 저장] 하면 여기에 쌓입니다.")
        return 0

    bundles = sorted({b for b, _s, _x, _y in pairs})
    print(f"고친 씬 {len(pairs)}개 · {len(bundles)}번들  ({', '.join(bundles)})\n")

    by_kind: dict[str, int] = collections.Counter()
    reps: collections.Counter[tuple[str, str]] = collections.Counter()
    for _b, _s, src, dst in pairs:
        by_kind[_kind(src, dst)] += 1
        for w in _words(src, dst):
            if w[0] or w[1]:
                reps[w] += 1

    print("── 갈래 ──────────────────────────────────────────")
    for k, v in by_kind.most_common():
        print(f"  {k:10s} {v:4d}곳")

    print("\n── 되풀이된 고침 (2회 이상 = 규칙 후보) ───────────")
    cand = [(w, n) for w, n in reps.most_common() if n >= 2]
    if not cand:
        print("  없습니다 — 아직 전부 한 번씩입니다. 규칙으로 올리지 마세요.")
    for (a, b), n in cand:
        arrow = f"{a or '(없음)'} → {b or '(지움)'}"
        print(f"  {n:3d}회  {arrow}")

    print("\n── 한 번만 나온 고침 (그 씬에 남겨 둡니다) ────────")
    once = [w for w, n in reps.most_common() if n == 1]
    for a, b in once[:12]:
        print(f"        {a or '(없음)'} → {b or '(지움)'}")
    if len(once) > 12:
        print(f"        … {len(once) - 12}개 더")

    if verify:
        print("\n── 검산: 규칙만으로 손수정과 같아지는가 ───────────")
        same = 0
        for b, si, src, dst in pairs:
            got = to_speech(src)
            if got == dst:
                same += 1
            else:
                print(f"  {b} 씬{si}")
                print(f"    손수정: {dst[:70]}")
                print(f"    규칙  : {got[:70]}")
        print(f"\n  규칙이 이미 따라잡은 것 {same} / {len(pairs)}")
        if same == len(pairs):
            print("  → 남은 손수정이 전부 규칙으로 재현됩니다. 새 회차는 손이 안 갑니다.")

    print("\n올릴 자리 — 용어는 vendor/chodangi/config/pronunciation_map.yaml,")
    print("            규칙은 core/speak.py, 집필 지시는 services/authoring/spec.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
