# axexam — 그누보드5 문제은행 + 질문권 Q&A

SQLD 등 IT 자격증 문제은행에 **회원제 + 질문권 기반 LLM Q&A**를 붙인다.
그누보드5 위에 **독립 디렉터리 앱(`/exam/`)** 으로 얹고 코어는 건드리지 않는다.

- 서버: 카페24 `axexam` · PHP 8.4 · MariaDB 10.6.17 · 콜레이션 `utf8mb3_general_ci`
- 설계 문서: [`_context/`](_context/) — [PLAN](_context/PLAN.md) · [COST](_context/COST.md) · [PAYMENT](_context/PAYMENT.md) · [HOSTING](_context/HOSTING.md) · [GNUBOARD-FACTS](_context/GNUBOARD-FACTS.md)
- 배포 절차: [`docs/DEPLOY.md`](docs/DEPLOY.md)

## 레이아웃

```
_context/          설계 문서 5종 (단일 진실 원천)
_probe/            서버 점검용 일회성 PHP — 올렸으면 확인 후 반드시 삭제
assets/present/    WOWPASS 디자인 자산 (폰트는 CDN 이라 번들 안 함)
data/              youtube_map.json — 수동 관리 입력 파일. 빌드가 덮어쓰지 않는다
docs/              DEPLOY.md 등
scripts/           빌드 파이프라인 (로컬에서 완결)
  exam_meta.py       02/ 메타 로더 — 과목·검수상태의 유일한 출처
  build_check.py     05 + 02 → 06/ 정적 산출물 + problems.json
  check_template.html
web/               서버로 올라갈 PHP (로컬이 원본, 서버는 사본)
  exam/  adm/  extend/
```

## 데이터 흐름

```
D:\00work\ocr-output-260723\
  02/  ← 단일 진실 원천 (300 md + _index.json). 과목·verified·needs_review 가 여기에만 있다
  05/  ← lesson JSON (문제 본문·보기·해설)
  06/  ← 빌드 산출물

02 + 05 ──► build_check.py ──┬─► 06/ (check.html, problems.js, figs, theory) ──FTP──► /www/exam/
                             └─► problems.json ──업로드──► adm/exam_import.php ──► ex_problem
```

⚠ 웹(`adm/exam_problem_form.php`)에서 고친 문제는 `edited_by` 가 채워져 재임포트에서 **건너뛴다**.
그 수정은 **주기적으로 `02/` 로 역반영**해야 한다 — 안 하면 언젠가 `02/` 가 낡아서 되돌아간다.

## 빌드

```bash
pip install -r requirements.txt

python scripts/exam_meta.py                                  # 메타 자체 점검
python scripts/build_check.py                                # 로컬 검증용 (StaticDS)
python scripts/build_check.py --api-base ./api/ --emit-json  # 서버 배포용 (ApiDS)
python scripts/build_check.py --init-youtube-map             # 유튜브 매핑 골격 1회
python scripts/build_check.py --prune                        # 예전 빌드의 mp4 411MB 정리
```

빌드 리포트에 **`과목 2종`** 이 찍혀야 한다. `1종`이면 subject 폴백 버그가 되살아난 것이다
(lesson JSON 블록에는 `subject` 키가 없어서 `"SQLD"` 로 폴백된다 — `exam_meta.py` 주석 참조).

## 하지 않는 것

- 그누보드 코어 수정 / 5.7 업그레이드 (master 대비 25커밋 뒤처진 diverged 브랜치)
- 영카트 사용 · cron · OIDC 자체 구현 · LMS 기능
- **LLM 초안 자동 승인** — `qa_draft` 와 `qa_answer` 를 분리한 것이 핵심 안전장치다
