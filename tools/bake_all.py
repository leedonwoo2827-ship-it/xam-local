# -*- coding: utf-8 -*-
"""05/ 번들 전체를 다시 베이크한다 (`_rounds` → deck.html · script.json · lesson.json).

**왜 이 파일이 필요한가.** `services/render/bake.py` 는 repo 안 어디에서도 호출되지
않았다 — 앱에 입구가 없었다(2026-08-12 확인). 그래서 슬라이드나 대본 규칙을 고쳐도
05/ 에 있는 옛 산출물이 그대로 남고, 렌더는 옛 모양으로 21시간을 돈다. 그 사고를
막는 입구다.

  python tools/bake_all.py            전부
  python tools/bake_all.py m01-1      일부만 (여러 개 나열 가능)
  python tools/bake_all.py --dry      쓰지 않고 1:1 만 검산

★ 모델을 부르지 않는다. 룰베이스 조립이라 72 번들이 몇 초~몇 분이다.
★ 번들 하나가 1:1(슬라이드↔캡처 씬)이 깨지면 그 번들만 건너뛴다 —
  `bake_one` 이 쓰기 전에 예외를 내므로 반쪽 파일이 남지 않는다.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ★ app.py 와 같은 방식으로 .env 를 읽는다. 이걸 빼면 XAM_AXEXAM 이 안 잡혀
#   `theme.tokens_css()` 가 `_ref\axexam` 을 보고 멈춘다(실측).
from dotenv import load_dotenv  # noqa: E402

load_dotenv(encoding="utf-8-sig")

from services.render import bake, bundles  # noqa: E402


def main(argv: list[str]) -> int:
    dry = "--dry" in argv
    codes = [a for a in argv if not a.startswith("-")]
    if not codes:
        codes = [b["code"] for b in bundles.scan_all()]
    if not codes:
        print("번들이 없습니다 — 05/ 경로와 XAM_BOOK 을 확인하십시오.")
        return 2

    print(f"{len(codes)} 번들" + (" (검산만, 쓰지 않음)" if dry else ""))
    ok, fail = 0, []
    for i, code in enumerate(codes, 1):
        try:
            if dry:
                lesson = bake.build_lesson(code)
                pages = bake.render.build_pages(
                    lesson, asset_dir="assets",
                    inline_dir=os.path.join(bake.BOOK_DIR, "02", "assets"))
                sc = bake.build_script(code, lesson, [m for _h, m in pages])
                n_cap = sum(1 for s in sc["scenes"] if s["capture"])
                if n_cap != len(pages):
                    raise ValueError(f"1:1 깨짐 — 페이지 {len(pages)} · 캡처 씬 {n_cap}")
                r = {"slides": len(pages), "scenes": len(sc["scenes"]), "capture": n_cap}
            else:
                r = bake.bake_one(code)
            ok += 1
            print(f"  [{i:>2}/{len(codes)}] {code:<8} 슬라이드 {r['slides']:>2} · "
                  f"씬 {r['scenes']:>2} · 캡처 {r['capture']:>2}")
        except Exception as exc:  # noqa: BLE001
            fail.append((code, str(exc)))
            print(f"  [{i:>2}/{len(codes)}] {code:<8} 실패 — {exc}")

    print(f"\n성공 {ok} · 실패 {len(fail)}")
    for code, msg in fail:
        print(f"  {code}: {msg}")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
