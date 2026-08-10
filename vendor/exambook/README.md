# vendor/exambook — 도구 #2(exambook-forge) 에서 들여온 순수 파이썬 파생부

출처: `D:\00work\260724-munje-sumary\exambook-forge\scripts\` (2026-08-10 복사)

| 파일 | 하는 일 |
|---|---|
| `build.py` | `_rounds/mNN.json` → `02/*.md` · `04/lesson_mNN.json` · `02/assets/*.svg` · `02/_index.json` · `02/difficulty_stats.json` |
| `validate.py` | `_rounds/*.json` 규약 검사 (오류/경고) |

## 왜 옮겼는가

**둘 다 LLM 을 안 부른다.** `build.py` 머리말이 *"표준 라이브러리만 사용"* 이라고
적어 뒀고, 실제로 `anthropic`/`openai`/API 키 참조가 0건이다. 모델이 필요한 곳은
`_rounds/mNN.json` **자체를 쓰는 일**뿐이고 그건 `services/authoring/` 이 한다.

집필자(SME) PC 에는 `exambook-forge` 가 없다. 옆 저장소를 경로로 부르면 그 PC 에서
조용히 실패한다 — 그래서 앱 안으로 들였다. `vendor/chodangi`(렌더 엔진)와 같은 판단이다.

## 손대지 않는다

**한 줄도 고치지 않고 그대로 둔다.** 고쳐야 할 것이 생기면 원본을 고치고 다시 복사한다.
여기서 고치면 새 책을 처음부터 만드는 경로(#2)와 교정 경로(이 앱)의 산출물이 갈리고,
그건 `_rounds` 를 바이트 단위로 왕복 검증하는 이 앱에서 409 로만 드러난다.

호출은 `services/authoring/derive.py` 가 **서브프로세스로** 한다(import 하지 않는다) —
`build.py` 는 `main()` 에서 `argparse` + `sys.exit` 로 끝나는 CLI 이고, `for _s in
(sys.stdout, sys.stderr): _s.reconfigure(...)` 로 **프로세스 전역 인코딩을 바꾼다.**
import 하면 그것이 FastAPI 프로세스에 그대로 걸린다.
