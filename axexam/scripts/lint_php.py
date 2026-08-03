#!/usr/bin/env python3
"""우리 PHP 전체 문법 검사.

왜 필요한가
  이 저장소에는 그누보드 코어가 없어서 로컬에서 화면을 띄울 수 없다. 그래서 지금까지
  "업로드해 보고 백지가 뜨는지 확인"하는 것이 유일한 검증이었다.
  php -l 은 코어 없이도 문법 오류를 잡는다 — 백지 사고의 1원인이 그것이다.

사용
  python scripts/lint_php.py

⚠ 문법 검사는 문법만 본다. 없는 함수 호출·잘못된 SQL·런타임 오류는 못 잡는다.
  그건 여전히 서버에서 확인한다.

⚠ PowerShell 5.1 로 .ps1 을 쓰지 않는 이유: UTF-8 파일을 ANSI 코드페이지로 읽어
  한글 문자열이 깨지고 파서가 죽는다. 실측으로 확인했다.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# 윈도우 콘솔 기본 코드페이지(cp949)에서 한글·기호가 깨지거나 죽는다.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
TARGETS = ["web", "_probe"]


def find_php() -> str | None:
    """PATH → winget 설치 경로 순으로 찾는다.

    winget 은 설치 직후 PATH 를 갱신하지만 **이미 열려 있는 셸에는 반영되지 않는다.**
    그래서 PATH 에 없어도 실패로 보지 않고 winget 패키지 디렉터리를 직접 훑는다.
    """
    from shutil import which

    if (p := which("php")):
        return p

    local = os.environ.get("LOCALAPPDATA")
    if local:
        pkgs = Path(local) / "Microsoft" / "WinGet" / "Packages"
        if pkgs.is_dir():
            for cand in pkgs.rglob("php.exe"):
                return str(cand)
    return None


def main() -> int:
    php = find_php()
    if not php:
        print("php 를 찾지 못했습니다.  winget install PHP.PHP.8.4", file=sys.stderr)
        return 2

    files: list[Path] = []
    for t in TARGETS:
        d = ROOT / t
        if d.is_dir():
            files.extend(sorted(d.rglob("*.php")))

    if not files:
        print("검사할 .php 가 없습니다.", file=sys.stderr)
        return 2

    ok = bad = 0
    for f in files:
        rel = f.relative_to(ROOT).as_posix()
        # -d display_errors=1 은 CLI 기본값이지만 명시해 둔다.
        # E_ALL 이라야 PHP 8.4 의 deprecated 도 보인다(카페24가 8.4다).
        r = subprocess.run(
            [php, "-l", "-d", "display_errors=1", "-d", "error_reporting=E_ALL", str(f)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        out = (r.stdout or "") + (r.stderr or "")
        if r.returncode == 0 and "No syntax errors" in out:
            ok += 1
        else:
            bad += 1
            print(f"FAIL  {rel}")
            for line in out.strip().splitlines():
                line = line.replace(str(f), rel)
                if line.strip():
                    print(f"      {line}")

    print()
    print(f"문법 OK {ok}개 · 실패 {bad}개")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
