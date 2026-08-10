# -*- coding: utf-8 -*-
"""`_rounds/mNN.json` → `02/*.md` · `04/lesson_mNN.json` 파생.

`vendor/exambook/build.py` 를 **서브프로세스로** 부른다. import 하지 않는 이유는
`vendor/exambook/README.md` 에 적었다(그 파일이 프로세스 전역 인코딩을 바꾼다).

★ 이 단계는 **덮어쓰기다.** `build.py` 는 `_rounds` 를 진실로 보고 `02/`·`04/` 를
  통째로 다시 쓴다. 그래서 **로컬 교정이 있으면 되돌아간다.** 계획이 `bundle.py` 를
  서브프로세스로 부르지 말라고 한 것과 같은 위험이다(`bundle.py:961-962`).
  갓 집필한 회차에는 교정이 없으므로 안전하지만, 그것을 **확인하고** 넘어간다 —
  `guard_local_edits()` 가 `02/*.md` 가 `_rounds` 보다 새로운지 본다.
"""
from __future__ import annotations

import glob
import os
import subprocess
import sys
from typing import Any, Dict, List

from core.constants import BASE_DIR

VENDOR = os.path.join(BASE_DIR, "vendor", "exambook")


def _run(script: str, args: List[str], timeout: int = 300) -> Dict[str, Any]:
    """스크립트 1개 실행. stdout/stderr 를 사람이 읽을 문자열로 돌려준다."""
    path = os.path.join(VENDOR, script)
    if not os.path.isfile(path):
        return {"ok": False, "code": -1, "out": "",
                "err": f"{script} 가 없습니다: {path}"}
    try:
        p = subprocess.run(
            [sys.executable, path, *args],
            capture_output=True, timeout=timeout,
            # ★ text=True 를 쓰지 않는다. 자식이 cp949 콘솔을 가정해 reconfigure 하므로
            #   플랫폼 기본 디코딩에 맡기면 한글이 깨진다. 바이트로 받아 utf-8 로 읽는다.
            cwd=VENDOR,
        )
        dec = lambda b: (b or b"").decode("utf-8", errors="replace")  # noqa: E731
        return {"ok": p.returncode == 0, "code": p.returncode,
                "out": dec(p.stdout), "err": dec(p.stderr)}
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": -1, "out": "",
                "err": f"{script} 가 {timeout}초 안에 끝나지 않았습니다."}
    except OSError as e:
        return {"ok": False, "code": -1, "out": "", "err": f"{script} 실행 실패 — {e}"}


def guard_local_edits(book_dir: str, round_code: str) -> List[str]:
    """`02/*.md` 가 `_rounds` 보다 새로우면 파생이 그것을 되돌린다 — 목록을 돌려준다.

    ★ 완벽한 검사가 아니다(파일 시각이 전부다). 그래도 "그냥 덮었다" 보다 낫다 —
      되돌아간 교정은 웹에 올라간 뒤에야 드러난다.
    """
    rj = os.path.join(book_dir, "_rounds", f"{round_code}.json")
    if not os.path.isfile(rj):
        return []
    base = os.path.getmtime(rj)
    newer: List[str] = []
    for p in sorted(glob.glob(os.path.join(book_dir, "02", f"{round_code}-*.md"))):
        try:
            if os.path.getmtime(p) > base + 1:      # 1초 여유 — 같은 배치 저장 흡수
                newer.append(os.path.basename(p))
        except OSError:
            pass
    return newer


def validate_round(book_dir: str, round_code: str) -> Dict[str, Any]:
    """`validate.py` — 반입 뒤 규약 검사.

    ★ 인자가 `build.py` 와 **다르다.** `build.py` 는 `--book`, 이쪽은 `--rounds-dir`
      이다(둘 다 원본 그대로 두므로 여기서 맞춘다). `--book` 을 넘기면 argparse 가
      code=2 로 죽는데, 그 실패는 "검증을 안 돌린" 것과 화면에서 구별되지 않는다.

    ★ "정답 분포 편중 (각 8~17 권장)" 경고는 50문항용 하드코딩이라 80문항이면
      **항상 뜬다.** warns 라 통과다 — 화면에서 경고로만 보여 준다.
    """
    return _run("validate.py",
                ["--rounds-dir", os.path.join(book_dir, "_rounds"),
                 "--round", round_code])


def derive_round(book_dir: str, round_code: str, *,
                 dry_run: bool = False, force: bool = False) -> Dict[str, Any]:
    """`build.py` — `02/`·`04/`·SVG·`_index.json`·`difficulty_stats.json` 파생."""
    edits = guard_local_edits(book_dir, round_code)
    if edits and not force and not dry_run:
        return {
            "ok": False, "code": -1, "out": "", "blocked_by_edits": edits,
            "err": (f"{round_code}: `02/` 에 `_rounds` 보다 새로운 파일이 "
                    f"{len(edits)}개 있습니다 — 파생하면 그 교정이 되돌아갑니다.\n"
                    f"  {', '.join(edits[:6])}"
                    + (f" 외 {len(edits)-6}개" if len(edits) > 6 else "")
                    + "\n먼저 문항 교정 화면에서 내용을 확인하십시오. "
                      "그래도 덮으려면 force 로 다시 부르십시오."),
        }
    args = ["--book", book_dir, "--round", round_code]
    if dry_run:
        args.append("--dry-run")
    out = _run("build.py", args)
    out["blocked_by_edits"] = edits         # force 로 덮었어도 무엇을 덮었는지 남긴다
    return out
