# 배포 절차

대상 서버: **카페24 `axexam`** · `axexam.mycafe24.com` · 서버 `uws8-wpm-159` / `112.175.85.162`
웹루트: `/www/` (그누보드5가 웹루트에 설치돼 있다)

---

## 원칙 셋

1. **로컬 `web/` 이 유일한 원본이고 서버는 사본이다.** 서버에서 직접 편집하지 않는다.
   급해서 서버에서 고쳤으면 **즉시 내려받아 로컬에 반영**한다. 서버에는 이력이 없다.
2. **그누보드 코어를 절대 수정하지 않는다.** 우리 파일은 전부 배포본에 없는 이름
   (`exam_*`, `10_exam.php`, `/exam/`)이라 코어 업데이트에 덮이지 않는다.
3. **덮어쓰기 전에 백업한다.** 특히 그누보드 버전 업데이트 전에는 반드시.

---

## 파이프라인은 두 갈래다

### 갈래 A — 로컬에서 완결 (서버 불필요)

```
02/ 원본  ─┐
05/ lesson ┼─► scripts/build_check.py ─► 06/ 산출물 ─► FTP 업로드
data/youtube_map.json ┘                └─► problems.json ─► adm/exam_import.php
```

`06/check.html` 을 더블클릭(`file://`)하면 `window.EXAM_API` 가 비어서 `StaticDS` 가 선택되고
문제풀이·클라이언트 채점이 그대로 돈다. **여기서 검증하고 올린다.**

### 갈래 B — 서버에서만 검증 가능

`api/*.php`, `adm/exam_*.php`, `extend/10_exam.php`, `sql/schema.sql`.

로컬 검증 단계가 **없다**. `include_once('../../common.php')` 가 그누보드 설치본·세션·`$member` 를
요구하고, 정작 확인해야 하는 것들(utf8mb3↔utf8mb4 조인, PHP 8.4 deprecation, Apache 타임아웃,
WAF SQL POST 오탐, `upload_max_filesize`)이 **정의상 카페24에서만 재현된다.**

→ 편집 → 업로드 → 브라우저 새로고침이 편집 루프 그 자체다.

---

## 도구

| 용도 | 도구 |
|---|---|
| 대량 전송 · 백업 다운로드 · 그누보드 덮어쓰기 | **FileZilla** |
| PHP 편집 루프 (저장 시 자동 업로드) | **VS Code SFTP 확장** 또는 **WinSCP "원격 디렉터리 최신 유지"** |
| 되돌리기 | **git** (로컬) |

카페24는 SSH 를 공식 지원하므로 **FTP(21) 가 아니라 SFTP(22)** 로 붙는다 — 비밀번호가 평문으로
나가지 않는다. (플랜별로 다를 수 있으니 접속 테스트 필요.)
"FTP 국내에서만 접속 허용" 설정은 그대로 둔다.

⚠ **SFTP 접속 설정 파일(`.vscode/sftp.json`, `ftp-sync.json`)은 `.gitignore` 에 있다.**
비밀번호가 들어가므로 절대 커밋하지 않는다.

---

## 경로 매핑

| 로컬 | 서버 |
|---|---|
| `web/exam/` | `/www/exam/` |
| `web/adm/exam_*.php`, `web/adm/exam_lib/` | `/www/adm/` |
| `web/adm/admin.menu600.exam.php` | `/www/adm/` |
| `web/extend/10_exam.php` | `/www/extend/` |
| `web/exam/sql/*.sql` | `/www/exam/sql/` (`.htaccess deny` 필수) |
| `<book>/06/` 산출물 | `/www/exam/` (`check.html`, `assets/`, `figs/`, `theory/`, `*.js`) |
| `<book>/06/problems.json` | **업로드하지 않는다.** `adm/exam_import.php` 화면에서 업로드 |

**올리면 안 되는 것**: `problems.json`(임포트 화면으로), `*.mp4`, `_backup/`, `_probe/`,
`data/youtube_map.json`(로컬 입력 파일), `scripts/`, `_context/`, `.git/`

---

## 정적 산출물 빌드 → 업로드

```bash
# 1) 로컬 검증용 (StaticDS — file:// 로 열어 확인)
python scripts/build_check.py

# 2) 서버 배포용 (ApiDS — api/*.php 를 호출한다)
python scripts/build_check.py --api-base ./api/ --emit-json

# 3) 예전 빌드가 남긴 06/videos/*.mp4 (411MB) 정리
python scripts/build_check.py --prune
```

⚠ **`--api-base` 없이 빌드한 `check.html` 을 서버에 올리면 정적 모드로 동작한다** — 로그인·질문·
서버채점이 전부 죽는다. 서버용 빌드는 반드시 `--api-base ./api/` 를 붙인다.
(리포트 마지막 줄에 `EXAM_API = ...` 가 찍히는지 확인한다.)

빌드 후 확인:
- 리포트에 **`과목 2종`** 이 찍히는가 (1종이면 subject 버그가 되살아난 것)
- `06/videos/` 에 mp4 가 없는가
- `06/assets/fonts/` 가 없는가 (폰트는 CDN)

---

## 그누보드 업데이트 (5.6.x → 최신)

1. **FTP 전체 백업** → `_backup/YYYYMMDD/`
2. **phpMyAdmin DB export**
3. [GitHub 릴리스](https://github.com/gnuboard/gnuboard5/releases)에서 최신 받기
   (영카트 `shop/` 이 설치돼 있으므로 **전체 패키지**로)
4. 압축 풀고 **`data/` 를 통째로 제외**한 뒤 FTP 덮어쓰기
5. `/adm/` 접속 → DB 업그레이드 안내가 있으면 따른다
6. 회원가입 → 로그인 → 게시판 글쓰기로 실동작 확인
7. `git status` 로 내 파일이 그대로인지 확인 (이름이 겹치지 않으므로 원칙적으로 안전)

**절대 덮어쓰면 안 되는 것**: `data/`, `data/dbconfig.php`

---

## 릴리스 알림

그누보드5는 8주에 8개 릴리스가 나오고 보안 패치가 다수 포함된다.
[gnuboard/gnuboard5](https://github.com/gnuboard/gnuboard5) → **Watch → Custom → Releases** 를 켠다.

---

## 백업 주기

| 대상 | 방법 | 주기 |
|---|---|---|
| DB | phpMyAdmin export | 문제 임포트 전후 + 월 1회 |
| 사이트 파일 | FTP 다운로드 → `_backup/` | 그누보드 업데이트 전 |
| 문제 원본 `02/` | ⚠ **현재 git 밖에 있다** (`D:\00work\ocr-output-260723\`) — 백업 경로 미정 |
| 내 코드 | git push (GitHub 비공개) | 커밋마다 |
