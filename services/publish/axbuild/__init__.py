"""발행 빌더 — axexam 저장소의 `scripts/` 를 이 앱 안으로 들여온 것.

`02/` · `05/lesson` · `youtube_map` 을 읽어 `06/` (정적 페이지 + `problems.json`) 을
만든다. 서브프로세스로 부른다(`services/publish/buildcheck.py`).

## 원본과 다른 점 — 딱 한 줄

`build_check.py` 의 `ROOT` 만 고쳤다. 나머지는 원본 그대로다.
자세한 이유는 그 줄의 주석 참고.

## ★ patch_axexam 3건은 적용하지 않았다 — 이미 상류가 더 낫게 해결했다

업로드본은 `tools/patch_axexam.py` 로 세 가지를 고치라고 남겨 뒀다. 이 PC 의
axexam(`D:\\00work\\260729-new`, github `leedonwoo2827-ship-it/axexam`)을 실제로
확인해 보니 셋 다 **이미 해결돼 있고 방식이 더 낫다.**

| 패치가 하려던 것 | 상류의 현재 구현 |
|---|---|
| `--youtube-map` 플래그 신설 (품목별 매핑) | `youtube_map_path(pd_id)` 가 `data/youtube_map.<pd>.json` 을 자동 선택. 플래그가 필요 없다 |
| `emit(DETAIL, "sqld.html")` → `{pd}.html` | `detail.html` 하나로 굽고 `?pd=` 로 품목을 가른다 — 품목마다 파일을 만들지 않는다 |
| `detail_template.html` 파라미터화 | `{{BRAND}}` · `{{PD}}` 등으로 이미 전면 토큰화. 템플릿 주석에 "예전에는 SQLD 의 두 과목이 여기 박혀 있었다" 고 남아 있다 |

그래서 패치를 적용하면 **더 나은 구현을 되돌리는 셈**이 된다. `tools/patch_axexam.py`
는 지웠다. `services/publish/buildcheck.py` 는 `--youtube-map` 을 그 플래그가 있을
때만 넘기므로(있는지 검사한다) 지금 상태에서도 그대로 동작한다.

> ★ `--book` 과 `--pd` 는 계속 **절대 생략하지 않는다.** 둘 다 기본값이 SQLD 라서
>   하나만 빠지면 라이브 SQLD 문제은행을 덮어쓴다 — `pr_key` 가 겹치는 행을 UPDATE
>   하고 `pr_id` 는 보존되므로 되돌릴 수 없다. `buildcheck.require_pd()` 가 잡을
>   만들기 전에 끊는다.

> axexam 저장소 자체(그누보드5 PHP · `web/`)는 **웹의 원본이라 지우지 않는다.**
> 여기 들여온 것은 로컬에서 도는 빌더뿐이다.
"""
