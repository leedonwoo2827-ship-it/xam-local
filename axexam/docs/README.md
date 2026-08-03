# docs

## 운영자용 (절차서)

| 문서 | 내용 |
|---|---|
| [업로드-260731.md](업로드-260731.md) | **여기부터 본다.** 성적표 델타 12개 + 어제·그제에서 넘어온 것 |
| [운영자-매뉴얼.md](운영자-매뉴얼.md) | 관리자 화면 전체 사용법 |
| [운영-영상-유튜브업로드.md](운영-영상-유튜브업로드.md) | 해설영상을 미등록으로 올리고 오픈 시 공개 전환하는 절차. **영상 ID 가 바뀌는 함정** 포함 |
| [업로드-260730.md](업로드-260730.md) | (지난) 다품목 전환 · 마이그레이션 |
| [내일-체크리스트.md](내일-체크리스트.md) | (지난) 07-30 분 |
| [S0-checklist.md](S0-checklist.md) | 서버 위생 — 초기 1회. 완료됨(2026-07-29) |

> 서버에 뭐가 올라갔는지는 문서로 추적하지 않는다 — **`python scripts/deploy_check.py`** 가
> 공개 URL 로 직접 판정한다(업로드 누락 · 삭제 누락 · API 응답).

## 개발자용

| 문서 | 내용 |
|---|---|
| [DEPLOY.md](DEPLOY.md) | 배포 절차. **로컬에서 완결되는 것 vs 서버에서만 되는 것** 두 갈래 |
| [UPLOAD-NOW.md](UPLOAD-NOW.md) | 로컬 경로 → 서버 경로 대응표 |
| [BACKLOG.md](BACKLOG.md) | 지금 안 만들지만 결정은 해둔 것 (엑셀 임포트, SFTP, `02/` 역반영 …) |
| [편지-프로덕트2-3.md](편지-프로덕트2-3.md) | **인하우스 #2(집필)·#3(요약노트) 출력 계약.** `02/`·`03/` 이 어떤 형태여야 웹이 소비하는가 |

## 설계 문서

`../_context/` 에 있다 — [PLAN](../_context/PLAN.md) · [COST](../_context/COST.md) ·
[PAYMENT](../_context/PAYMENT.md) · [HOSTING](../_context/HOSTING.md) ·
[GNUBOARD-FACTS](../_context/GNUBOARD-FACTS.md)

실측으로 정정된 내용은 해당 문서에 직접 반영해 두었다
(예: HOSTING.md 의 `max_execution_time` 30초 정정, GNUBOARD-FACTS.md 의 관리자 토큰 체계).
