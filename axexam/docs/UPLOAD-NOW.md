# 지금 올릴 것 — 파일 대응표

로컬 루트 `D:\00work\260729-new\` · 서버 웹루트 `/www`

---

## 1단계 — 스키마 설치 (3+1 파일)

| # | 로컬 | 서버 | 비고 |
|---|---|---|---|
| 1 | `web\exam\sql\schema.sql` | `/www/exam/sql/schema.sql` | `exam`, `exam/sql` 폴더를 새로 만든다 |
| 2 | `web\exam\sql\master.sql` | `/www/exam/sql/master.sql` | |
| 3 | `web\exam\sql\.htaccess` | `/www/exam/sql/.htaccess` | ⚠ FileZilla 는 점파일을 숨긴다 → **서버(S) → 강제로 숨김 파일 보이기** 를 켠다 |
| 4 | `_probe\exam_install.php` | `/www/exam_install.php` | **웹루트 최상위** (`common.php` 와 같은 자리) |

### 실행

1. 먼저 **최고관리자로 로그인** — `https://axexam.mycafe24.com/bbs/login.php`
   (계정을 모르면 카페24 콘솔 → `서비스 접속관리 → 관리자 정보수정`)
2. `https://axexam.mycafe24.com/exam_install.php` 접속
3. 실행 전 상태(DB 콜레이션, `g5_member.mb_id` 콜레이션, SQL 파일 존재)를 확인
4. **[스키마 설치 실행]** 클릭
5. 결과 확인 — 아래가 전부 맞아야 한다

```
schema.sql   성공 16 · 실패 0        (SET NAMES 1 + CREATE TABLE 15)
master.sql   성공  3 · 실패 0
검증(1) 테이블 15/15 · InnoDB 아님 0
검증(2) 서로 다른 콜레이션 종류 1      ← 2 이상이면 조인에서 1267 이 난다
검증(3) 조인 성공. 결과 0행           ← ★ 0이어도 정상. 에러가 없어야 한다
검증(4) uq_month 컬럼 3/3 · Non_unique=0
```

6. **`/www/exam_install.php` 삭제** ← 잊지 않는다

---

## 2단계 — 관리자 화면 (3 파일, 순서 중요)

⚠ `admin.menu600.exam.php` 는 **맨 마지막에** 올린다.
`adm/admin.lib.php` 가 모든 관리자 페이지에서 이 파일을 include 하므로,
문법 오류가 있으면 **관리자 전체가 죽는다.** 앞의 둘을 먼저 검증하고 올린다.

| # | 로컬 | 서버 |
|---|---|---|
| 1 | `web\adm\exam_lib\problem.php` | `/www/adm/exam_lib/problem.php` (`exam_lib` 폴더 새로 만든다) |
| 2 | `web\adm\exam_import.php` | `/www/adm/exam_import.php` |
| 3 | **↑ 둘을 검증한 뒤** `web\adm\admin.menu600.exam.php` | `/www/adm/admin.menu600.exam.php` |

### 검증 (3번 올리기 전에)

주소창에 직접 연다 — 최고관리자는 메뉴 등록 없이도 통과한다:

```
https://axexam.mycafe24.com/adm/exam_import.php
```

- 화면이 뜨면 정상 → 3번을 올린다. `/adm/` 왼쪽에 **문제은행** 메뉴가 생긴다.
- 백지나 500 이면 그 파일만 지운다. 관리자는 살아 있다.

---

## 3단계 — 문제 임포트

`adm/exam_import.php` 화면에서 업로드:

```
D:\00work\ocr-output-260723\06\problems.json     (387KB)
```

기대값:

```
신규 300 · 갱신 0 · 변경없음 0 · 건너뜀 0 · 실패 0 · 회차 6행
```

**FTP 로 올리지 않는다.** 화면 업로드다 — 처리 후 서버에서 즉시 지워진다.

---

## 4단계 — 정적 산출물 (S5 이후)

문제풀이 화면은 `api/*.php`(S5)가 있어야 동작하므로 **지금 올리지 않는다.**
S5 가 끝나면 `--api-base ./api/` 로 다시 빌드해서 올린다.

| 로컬 (`D:\00work\ocr-output-260723\06\`) | 서버 | 크기 |
|---|---|---|
| `check.html` | `/www/exam/check.html` | 30KB |
| `assets\` | `/www/exam/assets/` | 32KB (폰트는 CDN) |
| `figs\` | `/www/exam/figs/` | 205KB (SVG 58) |
| `theory\` | `/www/exam/theory/` | 160KB |
| `theory.js` · `theory_content.js` | `/www/exam/` | 81KB — **이론은 DB 가 아니라 여기 구워져 있다** |
| `videos.js` | `/www/exam/` | 유튜브 매핑 (지금은 비어 있음) |
| `problems.js` | `/www/exam/` | 388KB. **정적 폴백 전용** — 서버에선 `api/problems.php` 가 이긴다 |

**올리지 않는 것**: `problems.json`(임포트 화면으로), `videos\`(mp4 411MB — `--prune` 으로 정리)

---

## 요약 — 무엇이 어디로 가는가

```
문제 300건  →  problems.json  →  [임포트 화면]  →  ex_problem 테이블
이론 요약   →  theory_content.js  →  [FTP]  →  /www/exam/   (DB 아님)
화면·도식   →  check.html, assets, figs  →  [FTP]  →  /www/exam/
서버 로직   →  api/*.php, adm/exam_*.php  →  [FTP]  →  /www/
```
