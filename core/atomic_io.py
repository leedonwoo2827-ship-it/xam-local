"""원자적 파일 쓰기.

평범한 `open("w") + json.dump` 는 첫 쓰기에서 파일을 잘라 버리고 그 다음에 내용을
채운다. 그 사이에 프로세스가 죽으면 잘린 파일 또는 빈 파일이 남는다. 우리가 쓰는
대상은 BOOK 트리의 원천 데이터(240문항)라서 그건 곧 데이터 유실이다.

임시 형제 파일에 쓰고 fsync 한 뒤 `os.replace` 로 갈아 끼운다.

★ aim-local 원본에서 두 곳을 고쳤다. 둘 다 바이트 충실도 문제다.
  1) `ensure_ascii=False` — 원본은 기본값(True)이라 한글이 \\uXXXX 로 escape 된다.
     실측한 02/_index.json 은 한글이 그대로 들어 있다.
  2) `newline=""`      — 원본은 텍스트 모드 기본 개행 변환을 쓴다. Windows 에서는
     "\\n" 이 "\\r\\n" 으로 바뀌어 나간다. 실측한 02/*.md 는 LF 전용(CRLF 0개)이다.
     이 한 줄이 없으면 240개 파일이 전부 바이트가 달라진다.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional


def atomic_write_json(
    path: str,
    data: Any,
    *,
    indent: Optional[int] = None,
    trailing_newline: bool = False,
) -> None:
    """`data` 를 JSON 으로 원자적으로 저장한다.

    임시 파일 이름에 PID 를 붙여, 같은 파일을 저장하는 두 프로세스가 rename
    대상에서 충돌하지 않게 한다.

    trailing_newline: 실측한 02/_index.json · difficulty_stats.json 은 끝에 개행이
        **없다**. 기본을 False 로 둔 이유다. 개행을 붙이는 파일이 생기면 그때 켠다.
    """
    text = json.dumps(data, ensure_ascii=False, indent=indent)
    if trailing_newline:
        text += "\n"
    atomic_write_text(path, text)


def atomic_write_text(path: str, text: str) -> None:
    """텍스트를 원자적으로 저장한다. 개행은 문자열 그대로 나간다(LF 유지)."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def backup_sibling(path: str, suffix: str = ".bak") -> bool:
    """저장 전 .bak 형제를 남긴다. 실패해도 저장을 막지 않는다."""
    if not os.path.isfile(path):
        return False
    try:
        with open(path, "rb") as src, open(path + suffix, "wb") as dst:
            dst.write(src.read())
        return True
    except OSError:
        return False
