# 호스팅 선정

조사일 2026-07-29. 공식 문서로 확인된 것과 확인 안 된 것을 엄격히 구분했다.

---

## 결정 — 카페24 뉴아우토반 **일반형** (월 1,500원, VAT 포함)

닷홈이 표면상 싸지만(900원) **이 프로젝트에서는 카페24다.** 결정 근거 셋:

### ① 우리는 SQL 문자열을 POST로 보낸다 — 닷홈 WAF가 위험하다

질문 내용에 `SELECT e.ename FROM emp e WHERE 1=1` 같은 게 담긴다. SQLD·정보처리기사 사이트의 본질이다. **닷홈은 정상 POST를 WAF가 406으로 죽인 사례가 있다**(비공식, 2025-03). 이건 **질문 등록 = 유료 기능의 핵심**을 막는 리스크이고 감수할 수 없다.

카페24도 WAF가 있고 외부 웹크론 403 사례가 있지만, 그건 **인바운드 해외 IP 이슈**이고 우리는 웹크론을 안 쓴다. 어느 쪽이든 §11의 `probe_waf.php`로 계약 전 테스트한다.

### ② 닷홈이 싸지도 않다 — 무료 SSL에 도메인 조건이 붙는다

| | 호스팅 연 | 도메인 연 | 합계 |
|---|---|---|---|
| **카페24 일반형** | 18,000원 | Porkbun .com 약 15,500원 (자유 선택) | **약 33,500원** |
| 닷홈 1.5G | 10,800원 | **닷홈 .com 24,000원**(갱신가, 강제) | 34,800원 **+ SSL 설치비 1회** |

닷홈 무료 SSL 조건이 **"닷홈에서 구매한 유료 호스팅과 도메인"** 이다. 900원의 이득이 도메인 차액으로 상쇄된다. **카페24는 SSL에 도메인 조건이 없어 도메인을 어디서 사도 된다.**

### ③ 카페24의 단점 둘은 우리에게 무해하다

| 카페24 단점 | 우리 영향 |
|---|---|
| cron 없음(공식) | **무해.** 만료·지급·초안생성을 전부 조회/클릭 시점 처리로 설계했다 (§1-③) |
| `allow_url_fopen`=Off(공식) | **무해.** 어차피 curl로 쓴다. 오히려 공식이 fsockopen을 권고하는 게 **아웃바운드가 열려 있다는 신호** |

거기에 **PHP 8.4 공식, SSH 공식, 무료 SSL 조건 없음, 폐업 위험 최저**가 붙는다.

### 절약형(500원) 대신 일반형을 권하는 이유

도메인 연결이 **1개 vs 2개**다. `adsp.도메인` 같은 서브도메인이 필요해질 수 있고 차이가 월 1,000원이다. ⚠ 절약형도 PHP 8.4·SSH가 되는지는 플랜별로 확인하지 못했다 → **확인 필요.**

### 신청 완료 — 2026-07-29

| 항목 | 값 |
|---|---|
| 서비스 아이디 | **`axexam`** |
| 대표 도메인 | **`axexam.mycafe24.com`** ← 웹호스팅 기본 도메인이 `mycafe24.com`임이 **확정** |
| 상품 | **뉴아우토반호스팅 일반형** |
| 기간 | **2026-07-29 ~ 2027-07-28 (12개월)** |
| 결제 금액 | **27,200원** → **월 2,267원** (신용카드, 결제번호 `20260729_366318104`) |
| 하드 용량 | **1,400MB** |
| **트래픽** | **4,000MB** ← §아래 폰트 경고 |
| 서버환경 | UTF-8 (PHP 8.4, mariadb-10.x) |
| DB 용량 | 서버내 **무제한** |
| 서버 | `uws8-wpm-159` / `112.175.85.162` |
| 자동설치 | 그누보드5 → `www` |
| 스팸 SHIELD | 미사용 |
| 자동연장 | **미사용** → 2027-07-28 만료 시 사이트가 죽는다. 캘린더 등록 필수 |

§5 요금표에 적은 "일반형 월 1,500원 VAT 포함"은 **실제와 다르다.** 12개월 27,200원 = **월 2,267원.** 구 아우토반 요금이거나 프로모션가를 본 것으로 보인다. 설치비 별도 여부는 매출전표에서 확인할 것(월 1,350×12 + 설치비 11,000 = 27,200 조합도 성립).

[COST.md](COST.md) §3의 "월 고정비 3,000~6,500원" 범위 안이라 손익 결론은 바뀌지 않는다.

### ⚠ 트래픽 4GB — 폰트 2MB가 P1 문제로 올라간다

`assets/fonts/PretendardVariable.woff2` = **2.06MB**다. 자체 호스팅하면:

```
4,000MB ÷ 2.06MB ≈ 신규 방문 1,940명에 트래픽 소진
```

브라우저 캐시가 있으니 재방문은 안 태우지만, **신규 방문 2천 명이 월 한도**라는 뜻이다. 마이캐쉬 잔액이 0원이고 트래픽 자동 리셋도 꺼져 있으므로 **초과하면 사이트가 멈춘다.**

→ **폰트 CDN 전환을 Phase 1 필수로 올린다.** [PLAN.md](PLAN.md) §7에서 "P2 개선 항목"으로 적었던 것을 정정했다. `shell.html`에 `<link>` 한 줄이고 배포물이 2.67MB → 약 600KB가 된다.

⚠ **4,000MB가 월 기준인지 일 기준인지 확인 필요.** 일 기준이면 여유가 크지만, 카페24 뉴아우토반은 통상 월 기준이다.

### probe.php 실측 결과 (2026-07-29) — 전부 통과

```
그누보드 : 5.6.13          ← ⚠ 구버전. 최신 5.6.34로 업데이트 필수
PHP      : 8.4.21p1        ← 그누보드가 8.4 에서 부팅됨. 8.2 로 내릴 필요 없음
실행시간 : 0초              ← 무제한
메모리   : -1               ← 무제한
DB 실제버전 : 10.6.17-MariaDB-log
DB 콜레이션 : utf8mb3_general_ci   ← ⚠ utf8mb4 아님. 스키마 대응 필요
curl / openssl / mysqli / mbstring / json / gd  → 전부 OK
성공  https://api.deepseek.com/
성공  https://api.tosspayments.com/
성공  https://accounts.google.com/.well-known/openid-configuration
```

**해소된 확인 필요 항목**

| 항목 | 결과 |
|---|---|
| **아웃바운드 curl** | ✅ **DeepSeek·토스·구글 3개 전부 성공.** Phase 2(LLM)·Phase 3(결제)·소셜로그인 모두 가능. 카페24가 `allow_url_fopen`은 Off로 두지만 curl 아웃바운드는 열려 있다 |
| **MariaDB 실제 버전** | ✅ **10.6.17** — 요구(10.6+) 충족. LTS. `-log`는 바이너리 로깅 활성 표시 |
| `max_execution_time` | ✅ **0 = 무제한.** "LLM 응답 20~30초가 여기서 죽는다"는 우려가 해소됐다. 단 **웹서버(Apache) 타임아웃은 별개**이므로 검수 화면의 "1건씩 직렬 호출" 설계는 유지한다 |
| `memory_limit` | ✅ **-1 = 무제한** |
| PHP 확장 | ✅ `curl`·`openssl`·`mysqli`·`mbstring`·`json`·`gd` 전부 |
| PHP 8.4 + 그누보드 | ✅ `common.php` include가 정상 동작 = 부팅됨. **회원가입·로그인·글쓰기는 별도 테스트 필요** |

**새로 발견된 할 일 2개**

**① 그누보드 5.6.13 → 5.6.34 업데이트 (보안, 필수)**

자동설치가 **21개 버전 낡은 것**을 깔았다. 그 사이에 **v5.6.27의 대량 보안 패치**가 있다 — Blind SQL Injection, 명령 인젝션(RCE), Stored XSS, 관리자 엔드포인트 CSRF 누락, 포인트 Double Spend(§12 참조). **현재 이 취약점들이 살아 있다.**

방법: [GitHub 릴리스](https://github.com/gnuboard/gnuboard5/releases)에서 5.6.34 → **`data/` 폴더 제외**하고 FTP 덮어쓰기 → `/adm/`에서 DB 업그레이드 안내가 있으면 따른다.

**② 콜레이션 `utf8mb3_general_ci` — 스키마 대응**

utf8mb3는 옛 "utf8"로 **3바이트 문자만** 저장한다 → **이모지·일부 한자가 저장되지 않는다.** 그런데 `ex_*`를 utf8mb4로 만들면 `g5_member`(utf8mb3)와 조인 시 collation 충돌이 난다.

→ **섞어 쓴다.** 테이블 기본은 utf8mb4, `mb_id` 컬럼만 그누보드와 동일 콜레이션:

```sql
CREATE TABLE ex_qna (
  mb_id VARCHAR(20) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci NOT NULL,
  qa_question MEDIUMTEXT NOT NULL,      -- 테이블 기본 utf8mb4 → 이모지 OK
  ...
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

`mb_id`는 영문+숫자라 utf8mb3로 충분하고 질문 본문은 이모지가 들어간다. [PLAN.md](PLAN.md) §4 전체에 적용할 것.

### 지금 켜야 할 설정 2개

| 설정 | 현재 | 바꿀 것 | 이유 |
|---|---|---|---|
| **트래픽 알림 수신** | 수신 안함 | **켜기** | 4GB 한도. 알림 없으면 모르고 사이트가 멈춘다 |
| **하드 알림 수신** | 수신 안함 | **켜기** | 1.4GB. 로그·백업이 쌓이면 찬다. 공짜다 |

### 그대로 둘 것

| 설정 | 현재 | 판단 |
|---|---|---|
| **MySQL 외부 IP 접근** | 사용 안함 | **끈 채로 둔다.** DB를 인터넷에 노출할 이유가 없다. 백업은 phpMyAdmin 수동 export로 시작하고, 문제 임포트는 `adm/exam_import.php`로 하므로 외부 접속이 불필요하다 |
| **FTP 국내에서만 접속 허용** | 국내만 | 그대로. 보안상 유리 |
| **트래픽 자동 리셋 / 마이캐쉬 0원** | 사용 안함 | 그대로. 초과 시 멈추는 게 무한 과금보다 낫다. 대신 알림을 켠다 |
| **자동연장** | 미사용 | 그대로(1년 뒤 방향이 바뀔 수 있다). **만료일을 캘린더에 넣는다** |

### 나중에 할 것

- **세금계산서 신청** — 사업자등록 후. 비용 처리에 필요하다
- **게시판 스팸필터 관리** — 스팸 SHIELD와 별개 메뉴로 보인다. 지금은 건드리지 말고, **질문 POST가 막히면 여기를 먼저 본다**
- **진단하기** — 지금 눌러서 설치 상태를 점검한다

### 신청 설정 근거

| 항목 | 근거 |
|---|---|
| **서버환경** | **PHP 8.4 / mariadb-10.x UTF-8** | 8.2는 2026-12-31 보안지원 종료(5개월). 콘솔에서 버전 변경 가능하므로 되돌릴 수 있다 |
| **프로그램 자동 설치** | **그누보드5** | DB 생성·접속정보·`data/` 권한을 대신 해준다 |
| **설치 경로** | **`www`** (`www/gnuboard5` 아님) | 그누보드가 웹루트여야 `/exam/`이 `도메인/exam/`이 되고 `include_once('../../common.php')`가 성립한다 |
| **스팸 SHIELD** | **미사용** | 질문 POST에 SQL 문자열이 담긴다. 봇/스팸 필터 오탐이 질문 등록을 막을 수 있다. 로그인 필수 회원제라 익명 스팸 경로가 좁고, 그누보드에 kcaptcha가 있다. 스팸이 실제로 오면 그때 켠다 |

### 설치 직후 확인 3개 (반드시)

1. **그누보드 버전** — `version.php`의 `G5_GNUBOARD_VER`. **`5.6.34`가 아니면** 최신을 받아 덮어쓴다(`data/`와 `data/dbconfig.php`는 보존). 8주에 8개 릴리스가 나오는 스택이라 구버전은 보안 패치가 빠져 있다
2. **`/install/` 폴더 삭제 여부** — 자동설치가 지웠는지 확인. 남아 있으면 **재설치로 사이트를 날릴 수 있는 구멍**이다
3. **PHP 8.4에서 실제로 도는지** — 회원가입 → 로그인 → 게시판 글쓰기. `Deprecated:` 경고가 화면에 뜨면 콘솔에서 **8.2로 내린다**. 그누보드5는 오래된 코드라 8.4의 implicit nullable 파라미터 deprecation에 걸릴 수 있다. **코어를 고치지 않는다**(§11 원칙)

그다음 `probe.php` + `probe_waf.php`(§11) 실행. **DB 실제 버전과 아웃바운드 curl 3개가 이 프로젝트의 생사를 가른다.**

### 계정 아이디 — `axexam`

카페24 계정 아이디는 **FTP 계정 · DB명 · 서브도메인을 겸하고 보통 변경 불가**다. 커스텀 도메인을 붙인 뒤에도 관리 화면에서 계속 보인다.

| 항목 | 상태 |
|---|---|
| `axexam.com` | **미등록 확인** (2026-07-29, RDAP) → 커스텀 도메인 살 때 문자열 유지 가능 |
| 길이 | 6자 |
| 계보 | 기존 아이비 아이디 `axubion`과 `ax` 접두가 이어진다 |
| 성격 | `exam` = **평가 솔루션**. 자격증명에 묶이지 않아 과정 확장에 열려 있다 |
| 기본 도메인 | ⚠ 웹호스팅 기본 도메인이 `mycafe24.com`인지 **확인 필요** (쇼핑몰은 `.cafe24.com`) |

**선정 과정에서 막힌 것들**: `itcert` · `itpass` · `certpass` · `itcert24` · `itmunjebank` 등 — 카페24는 20년+ 서비스라 **흔한 영단어 조합은 8자 이하도 대부분 선점**됐다. `ax`/`ubion` 같은 회사 고유어 접두가 선점을 피하는 실용적 해법이었다.

**피한 것**: `e-` 접두(e-test·e-learning은 2000년대 초 스타일이고, 사내 구 프로그램명이기도 함), 시험명 직접 삽입(`sqld`/`adsp`/`gisa`/`comhwal` — 확장이 막히고 시행기관 상표 이슈 소지).

**검토 후 보류한 대안**: `axassess`(평가 성격 강하나 철자 오류 위험) · `geomjeong`(검정, 콴다 계보이나 9자) · `chaejeom`(채점) · `ubionexam`(B2B 신뢰도 높으나 회사명을 박으면 별도 브랜드로 못 쓴다). 전부 `.com` 미등록 상태였다.

### 계약 전 반드시 확인 (§10·§11)

1. **MariaDB 정확한 마이너 버전** — "10.x"로만 표기돼 있다
2. `curl`·`openssl` 확장 활성화 여부
3. `max_execution_time` 기본값과 `ini_set` 허용 여부 — **LLM 응답 20~30초가 여기서 죽는다**
4. `api.deepseek.com`·`api.tosspayments.com` curl 호출 허용
5. **`1=1`·`UNION ALL`이 든 POST가 WAF를 통과하는가**

---

## 순위 (전체 조사 결과)

**요구사항을 전부 공식 문서로 충족하는 국내 웹호스팅 업체는 없다.** PHP 확장 목록·리소스 한도·상업적 이용 약관은 **조사한 13개 업체 전부 미기재**다. 아래 순위는 "공식 확인된 항목이 가장 많고 결정적 결격이 없는 순"이다.

| 순위 | 업체 | 월 요금 | 결정적 근거 | 결정적 단점 |
|---|---|---|---|---|
| **1** | **카페24 뉴아우토반 일반형** | **1,500원 (VAT 포함)** | PHP 8.4 공식, SSH 공식, 무료 SSL 공식, 폐업 위험 최저 | cron 없음(공식), `allow_url_fopen`=Off(공식), MariaDB 마이너 미기재 |
| **2** | **닷홈 1.5G 웹호스팅** | **900원 (VAT 포함)** | PHP 8.4, MySQL 8.x, SSH, **LE 90일 자동연장 공식 명시** | 무료 SSL에 **닷홈 도메인 구매 조건**, MySQL 버전 신청 후 변경 불가, WAF 406 사례 |
| **3** | 나우호스팅 Nano | 10,000원 | **국내 유일 공유호스팅 cron 공식 명시**, MariaDB 11 | 최저가가 카페24의 6.7배, 부가세·SSH·확장 전부 미기재 |

**아이비호스팅은 탈락이다** (§3).

---

## 1. 조사 전체를 규정하는 발견 3가지

### ① PHP 8.0·8.1은 이미 보안 지원이 끝났다

php.net 공식 지원 버전 표에 **8.0·8.1이 아예 등재되어 있지 않다.** 현재 보안 지원을 받는 최소 버전은:

| 버전 | 보안 지원 종료 |
|---|---|
| PHP 8.2 | **2026-12-31** (5개월 남음) |
| PHP 8.3 | 2027-12-31 |
| PHP 8.4 | 2028-12-31 |

출처: https://www.php.net/supported-versions.php

→ **PLAN.md의 "PHP 8.1 또는 8.2" 권고는 정정한다. 최소 8.2, 권장 8.3 또는 8.4다.** 8.2도 5개월 뒤면 EOL이므로 신규 구축은 8.3+로 간다.

→ 이것 하나로 **아이비호스팅(상한 8.0)은 탈락**이다.

### ② 카페24는 `allow_url_fopen`을 공식적으로 Off로 둔다

공식 문서 원문:

> "저희 카페24에서는 **기본적으로 해당 기능이 모두 off 로 설정**이 되어 있으며 … 다른 방법으로 구현을 하시거나 … **(HttpRequest, http_get, fsockopen 등의 함수로 구현이 가능합니다.)** … 반드시 allow_url_fopen 을 사용하셔야 한다면 고객센터로 문의"

출처: https://cafe24.zendesk.com/hc/ko/articles/18319303326489

→ `file_get_contents('https://api.deepseek.com/...')`는 **안 된다. 반드시 curl로 쓴다.**

→ **역으로 이게 좋은 신호다.** 공식 문서가 fsockopen을 대안으로 권고한다는 것은 **네트워크 레벨 아웃바운드가 열려 있다**는 뜻이다.

### ③ 카페24는 공유 웹호스팅에서 스케줄러를 공식 거부한다

> "리눅스 웹호스팅에서는 MySQL/MariaDB의 **event_scheduler 설정이 불가**합니다."
> "웹호스팅(공유호스팅)은 서버 자원을 다수의 사용자가 공유하는 환경이므로, 서버 안정성을 위해 event_scheduler 설정을 지원하지 않습니다."

출처: https://help.cafe24.com/faq/web-hosting/introduce/setup-management/event-scheduler-setting/

cron은 **단독웹호스팅/서버호스팅 상품의 기능**으로 안내된다. 출처: https://help.cafe24.com/faq/server-hosting/introduce/linux-setup-management/cron-system-scheduling/

→ **우리 설계가 cron을 쓰지 않기로 한 게 정확히 맞았다.** 크레딧 만료는 조회 시점 판정(lazy expiry), LLM 초안은 관리자 검수 화면 진입 시 트리거. **cron을 요구사항에서 뺀 것이 호스팅을 바꾸는 것보다 싸다.**

---

## 2. PHP / DB 버전 비교표

| 업체 | 선택 가능 PHP (최고) | **MySQL/MariaDB 정확 버전** | DB 용량 |
|---|---|---|---|
| **카페24 뉴아우토반** | 7.4 / 8.2 / **8.4** | "MariaDB 10.x" — 마이너 **미기재** | 무제한(서버 공간 내) |
| **닷홈** | 5.6 / 7.0 / 7.2 / 7.4 / 8.0 / 8.2 / **8.4** | "MySQL 8.x" — 마이너 **미기재**. 신청 후 **변경 불가** | 무제한 |
| **나우호스팅** | 5.4~**8.4** | "MariaDB 11" — 메이저만, 마이너 **미기재** | Nano DB 3GB~ |
| **가비아** | 5.3~7.4 / **8.4 / 8.5** | MySQL 4.0 / 5.0 / 5.5 / 5.6 / 5.7 / **8.0** ← 상한 8.0, MariaDB 없음 | 미기재 |
| **미리내** | 공지: 8.0 / **8.2** (2024-01-02) ⚠️ 상품페이지는 "5.x/7.x" | **MariaDB 10.6** ← **정확한 번호를 표기한 유일한 곳** ⚠️ 상품페이지는 "MYSQL 5.0.77"로 상충 | 미기재 |
| **아이비호스팅** | 5.2 / 5.6 / 7.2 / 7.4 / **8.0** ← EOL | "MariaDB 10.x" — 마이너 미기재 | 무제한 |
| **스쿨호스팅** | 5.6 / 7.0 / **8.1** ← EOL | MySQL **5.0 / 5.7** ← 낡음 | 상품별 |
| **iwinv** | "7.x ~ 8.x" — 마이너 미기재 | **확인 필요** — 공식 매뉴얼에 명시 없음 | 프리미엄 100MB / 무제한 5GB |
| **후이즈** | **확인 필요** | **확인 필요** — 사양 페이지가 SSO 리다이렉트로 비로그인 조회 불가 | DB 150MB~1GB |
| **웹티즌** | **확인 필요** | **확인 필요** — HTTP 403 봇 차단 |확인 필요 |
| **코리아호스팅** | PHP 5.3 (2014년 문서) | MySQL 5.5 (2014년 문서) | — |
| 벤처스토어 | — | — | **DNS 미해석 + 웨이백 0건 → 사실상 소멸** |
| cloudv | — | — | **공유 웹호스팅 상품 없음** (VPS 전용, 웹호스팅은 ivyro로 링크) |

---

## 3. 아이비호스팅으로 그냥 가도 되는가 → **아니오**

| 항목 | 공식 기재 | 결론 |
|---|---|---|
| PHP 버전 | **기재됨: 5.2 / 5.6 / 7.2 / 7.4 / 8.0** | ❌ **상한 8.0 = php.net 보안 지원 종료.** 이것만으로 결격 |
| MariaDB 버전 | "MariaDB 10.x"로만 기재 | ⚠️ "SQL 버전 낮은 듯"이라는 의심을 **해소할 근거가 공식 문서에 없다** |
| cron | **언급 자체가 없음** (상품표·매뉴얼 8개 항목·FAQ 전부 확인) | ⚠️ 미지원인지 미기재인지 판별 불가 |
| outbound | 명시 없음. 단 상품표에 **"과도한 국제 트래픽 발생시 이용제한"** | ⚠️ **리스크.** DeepSeek·Google OIDC 모두 해외 |
| SSH | **"미지원"으로 명시** | ❌ composer/git 불가 |
| DB 원격접속 | **"미지원(localhost만)"으로 명시** | 운영은 phpMyAdmin으로만 |
| 요금 | 라이트 750원 / 베이직 1,500원, **부가세 별도, 설치비 15,000원** | 카페24 일반형(1,500원 VAT포함)보다 비싸다 |

**부수 정보 (공식)**: 아이비는 **CPU/RAM 30% 이상 점유 시 선조치 후 통보** 차단 정책을 공지한다. 반면 웹방화벽은 **마이페이지에서 직접 on/off 가능** — 이건 닷홈·카페24보다 나은 점이다(둘은 CS 요청 필요).

**앞선 조사와 달라진 점**: 유료 플랜도 PHP 상한은 8.0이 맞고(무료와 동일), SSH는 "언급 없음"이 아니라 **"미지원"으로 명시**되어 있었다.

→ **이전한다.** 설치비 15,000원은 회수 불가 매몰비용이므로 미련 두지 않는다.

출처: [상품 사양표](https://www.ivyro.net/html/webht/hosting/?type=secure), [매뉴얼 목차](https://www.ivyro.net/html/manual/manual_1.php), [과부하 차단 안내](http://notice.ivyro.net/overload/), [웹방화벽 차단 안내](http://notice.ivyro.net/modsecurity/waf.html)

---

## 4. 기능 비교표 — cron / outbound / SSH / SSL

| 업체 | cron(공유) | 외부 HTTP outbound | SSH 실쉘 | 무료 SSL |
|---|---|---|---|---|
| **카페24** | **미지원**(공식). event_scheduler 공식 불가 | **`allow_url_fopen`=Off 공식.** curl/fsockopen으로. curl 확장 제공 여부는 미기재 → **확인 필요** | **지원**(공식) | **무료 제공**(기본도메인) |
| **닷홈** | 미기재 → 확인 필요 | 미기재 → 확인 필요. "소켓 통신 이용 메일 발송 불허" 문구만 | **지원**(공식 표) | **Let's Encrypt, 90일 자동연장** ✅ 단 **닷홈 호스팅+닷홈 도메인 필수**, **설치비 1회**, 설치까지 1~2영업일 |
| **나우호스팅** | **"Cron관리" 공식 명시** ✅ (주기·방식 미기재) | 미기재 → 확인 필요 | 관리기능 목록에 없음 → 확인 필요 | **LE 무료, 원클릭 자동셋팅** ✅ |
| **아이비** | 미기재 | 미기재 + 국제 트래픽 제한 조항 | **미지원**(명시) | 상품표 언급 없음 → 확인 필요 |
| **가비아** | 미기재 | 미기재 | 사양표 "미지원" ⚠️ 고객센터에 SSH 보안설정 매뉴얼 존재 → **상충, 확인 필요** | 443 제공(무료 LE 명시 없음) |
| **iwinv** | 미기재 | ⚠️ 이용제한 조항에 **"API 호출/중계, 데이터 중계, 프록시 서버 용도로 사용시 이용 제한"** ← **요구사항과 정면 충돌** | cPanel 상품엔 SSH·Git 문서화. 비-cPanel은 FTP/SFTP만 | "CA 등급 SSL/TLS 무료"(발급기관·자동갱신 미기재) |
| **스쿨호스팅** | 미기재 | 미기재. ⚠️ 검색에 걸리는 `allow_url_fopen=Off`·`wget/curl 접근제한` 문서는 **웹호스팅이 아니라 "가상서버호스팅" 이용안내서** 소속 | "SSH와 SFTP를 지원" — 실쉘 여부 미기재 | 443 제공, 인증서 별도 |
| 후이즈·웹티즌·코리아호스팅 | **확인 필요 (전 항목)** | 확인 필요 | 확인 필요 | 확인 필요 |

### 전 업체 공통으로 공식 문서에 없는 것

계약 전 서면 문의 필수.

| 항목 | 결과 |
|---|---|
| **PHP 확장 목록** (`curl`, `openssl`, `mysqli`, `mbstring`, `json`) | **13개 업체 전부 미기재.** 코리아호스팅만 "Curl 등 포함" 문구, 미리내는 eAccelerator/ionCube/Zend만 표기 |
| **`max_execution_time` / `memory_limit`** 기본값·변경 가능 여부 | **전 업체 미기재.** `.htaccess`/`php.ini`/`ini_set` 허용 여부를 공식화한 곳 없음 |
| **상업적 용도 허용 명시** | **전 업체 미기재.** 유료 플랜이니 통상 허용이겠지만 약관 문구를 찾지 못했다 |

---

## 5. 요금 / 계약 조건

| 업체 | 최저 유료 플랜 | 월 요금 | VAT | 설치비 | 도메인 연결 |
|---|---|---|---|---|---|
| **카페24** | 절약형 / **일반형** | 500원 / **1,500원** | **포함** | 미기재 | 1개 / 2개 |
| **닷홈** | 1.5G 웹호스팅 | **900원** (12개월 기준) | **포함** | 미기재 | 미기재 |
| iwinv | 스타터 | 600원(할인 310원) | 확인 필요 | 미기재 | 상품별 |
| 아이비 | 라이트 / 베이직 | 750원 / 1,500원 | **별도** | **15,000원** | 2개 / 5개 |
| 스쿨호스팅 | 절약형 | 400원 | **별도** | **10,000원** | 1개 |
| 미리내 | FULL SSD 500M | 2,000원 | 확인 필요 | 확인 필요 | 확인 필요 |
| 가비아 | 베이직 | 4,950원 | **포함** | 확인 필요 | 확인 필요 |
| 나우호스팅 | Nano | **10,000원** ⚠️ 상품페이지에 "월 5,000원" 표기도 있어 상충 | 확인 필요 | 확인 필요 | 무제한 |
| 후이즈 | 라이트 | 11,800원 | **별도** | **10,000원**(타사 도메인 20,000원) | 확인 필요 |

---

## 6. 순위 상세

### 1순위 — 카페24 뉴아우토반 일반형 (1,500원/월, VAT 포함)

**결정적 근거**
- **PHP 8.4 공식 지원**(보안 지원 2028-12-31까지) + 관리콘솔에서 버전 변경 공식 안내 ([변경 가이드](https://help.cafe24.com/faq/web-hosting/introduce/new-renewal-change/change_server_environment_php_version/))
- **SSH 공식 지원** — 국내 공유호스팅 중 이걸 상품표에 명시한 몇 곳 중 하나
- 커뮤니티에 2026-07 Composer 설치 성공 사례(비공식, [sir.kr/questions/565721](https://sir.kr/questions/565721)) → **아웃바운드 443이 열려 있다는 정황 증거**
- 무료 SSL 공식, 기업 규모·문서화가 가장 낫고 **폐업 위험이 가장 낮다**

**결정적 단점**
- **cron 없음(공식).** event_scheduler도 공식 불가 → 우리 설계가 cron을 안 쓰므로 무해하다
- **`allow_url_fopen`=Off(공식).** LLM 호출은 반드시 curl로
- **MariaDB 마이너 버전 미기재** — 최대 관심사가 정작 확인 안 됨
- 외부 웹크론(cron-job.org) 호출이 WAF/해외IP로 403 맞은 실사례(비공식, 2026-04, [sir.kr/questions/564152](https://sir.kr/questions/564152))

### 2순위 — 닷홈 1.5G 웹호스팅 (900원/월, VAT 포함)

**결정적 근거**
- **PHP 8.4 공식** + 5.6~8.4 선택
- **MySQL 8.x** — 8.0이면 MariaDB 10.x보다 최신 계열
- **SSH 공식 지원**
- **무료 SSL이 Let's Encrypt이고 90일 자동연장임을 공식 명시** — 이걸 문서로 확인한 유일한 대형사 ([SSL 페이지](https://www.dothome.co.kr/etc/ssl/price.php))

**결정적 단점**
- **MySQL 버전을 신청 후 변경 불가**(공식)
- 무료 SSL에 **닷홈 도메인 구매가 조건** + 설치비 1회 + 1~2영업일 → 도메인이 닷홈에 묶인다
- cron 미기재
- ⚠ **WAF가 정상 POST를 406으로 죽인 사례**(비공식, 2025-03, [sir.kr/boards/free/1705793](https://sir.kr/boards/free/1705793)) — **지문에 SQL이 들어가는 우리 사이트에서 실제 리스크다.** 질문 POST에 SQL 문자열이 담기면 WAF가 SQL 인젝션으로 오탐할 수 있다

### 3순위 — 나우호스팅 Nano (10,000원/월)

**결정적 근거**
- **국내에서 유일하게 공유 웹호스팅에 "Cron관리"를 공식 명시** ([상품 페이지](https://nowhosting.kr/bbs/page.php?hid=webhosting))
- **PHP 8.4 + MariaDB 11** — 조사 대상 중 DB 메이저 버전 최고
- LE 원클릭 무료, 도메인·서브도메인 무제한 연결

**결정적 단점**
- **최저가 10,000원** = 카페24 일반형의 약 6.7배
- 부가세/설치비/약정/SSH/PHP 확장 **전부 미기재**
- 상품 페이지 간 요금 표기 상충(10,000원 vs 5,000원)
- 소규모 업체 → 폐업·정책 변경 리스크

### 순위권 밖

| 업체 | 탈락 이유 |
|---|---|
| **아이비호스팅** | PHP 8.0 EOL, SSH 미지원 명시, DB 원격접속 불가 |
| **가비아** | MySQL 8.0이 상한, SSH 상충, 4,950원 |
| **스쿨호스팅** | MySQL 5.7, PHP 8.1 EOL |
| **iwinv** | ⚠ **"API 호출/중계 용도 이용 제한" 조항이 요구사항과 정면 충돌.** 2025-12 무통보 정책변경 사례도 있음 |
| **코리아호스팅** | 2014년 기준 문서(PHP 5.3 / MySQL 5.5) |
| **벤처스토어** | 소멸 |
| **후이즈·웹티즌** | 공식 사양 확인 자체가 불가 |

---

## 7. "국내 웹호스팅 DB 버전이 낮다"는 인식 — 절반만 맞다. 다른 이유로 맞다

**낮지 않은 곳 (버전 번호 기준)**
- 나우호스팅 **MariaDB 11** — 조사 대상 최고
- 미리내 **MariaDB 10.6** — 정확한 번호를 표기한 유일한 곳
- 닷홈 **MySQL 8.x**
- 카페24 **MariaDB 10.x**

**실제로 낮은 곳**
- 스쿨호스팅 **MySQL 5.0 / 5.7**
- 가비아 — MySQL 8.0이 상한이지만 **4.0·5.0까지 선택 목록에 남아 있다**
- 코리아호스팅 **MySQL 5.5** (2014년 문서)

**진짜 문제는 버전이 아니라 표기다.** 카페24·아이비·나우호스팅은 **"10.x" "11"처럼 메이저만 적고 마이너를 안 밝힌다.** iwinv·후이즈·웹티즌은 **제공 DB 버전을 아예 안 적는다.**

→ 불만은 "버전이 낮다"보다 **"버전을 알 수 없다"** 로 재정의하는 게 정확하다. MariaDB 10.x는 10.0(2014)부터 10.11(2023 LTS)까지 **9년 폭**이라 "10.x"는 사실상 정보가 아니다.

**PHP 쪽은 인식이 오히려 낡았다.** 2022년 자료에서는 국내 대부분이 PHP 7.4 상한이었지만([wpnews 2022-06-18](https://wpnews.co.kr/국내-호스팅업체-신규-설치-시-지원-php-버전-목록-정리/)), 2026년 현재 **카페24·닷홈·나우호스팅·가비아가 PHP 8.4를 공식 지원**한다. 뒤처진 건 **아이비(8.0)·스쿨호스팅(8.1)** 이다.

---

## 8. 다른 층위 — VPS / PaaS (밀지 않는다)

관리 부담을 싫어하고 PHP를 원한다는 전제이므로 강하게 밀지 않는다. 다만 알아둘 가치는 있다.

### 국내 저가 VPS

| 제공사 | 사양 | 월 요금 | 관리 주체 |
|---|---|---|---|
| **iwinv** `vgna_1_n` | 1vCPU / 1GB / 25GB NVMe | **5,600원 (VAT 별도)** → 약 6,160원 | 고객 (OS·백업 전부) |
| **카페24** 리눅스 가상서버 일반형 | 1GB / 30GB SSD / 월 300GB | **7,000원 (VAT 포함)** + 설치비 22,000원 ⚠️ 현재 **품절 표시** | 고객 (root) |
| 가비아 VPS | — | **확인 필요** — 공식 상품 페이지가 404 |— |
| 네이버클라우드 Micro | 1vCPU/1GB | **확인 필요** — 정적 요금표 없이 JS 계산기만 | 고객 |

확인된 모든 VPS가 **"백업의 의무는 고객에게 있습니다"** 를 명시한다. 관리 부담 회피 요건과 정면 충돌.

### PaaS

- **Cloudtype** — 국내에서 **PHP를 공식 지원하는 유일한 PaaS.** PHP 7.3~8.2 자동 탐지(8.3+ 지원은 **확인 필요**), MariaDB 애드온 원클릭. **프리티어는 매일 1회 자동 중지**되어 상시 서비스 부적합. Hobby 6,600원/0.5GB부터. 앱+DB+디스크 구성 시 약 19,800원/월(VAT 포함, 공식 단가 합산). [Laravel 가이드](https://docs.cloudtype.io/guide/templates/laravel) / [요금제](https://cloudtype.io/pricing)
- **가비아 컨테이너 호스팅은 PHP 미지원** (Java/Python/Node.js만). [사양](https://webhosting.gabia.com/container/service/detail)
- **Vercel/Netlify는 PHP 서버 실행 불가** — Vercel은 커뮤니티 런타임만, Netlify는 빌드 타임 전용

### 설계로 회피한다

이 사이트의 요구사항 중 **cron이 정말 필요한 건 없다.** 크레딧 유효기간은 조회 시점 만료 판정(lazy expiry), LLM 초안 생성은 관리자 검수 페이지 진입 시 트리거. 이렇게 설계하면 **카페24/닷홈 공유호스팅으로 충분하고 cron 부재가 결격이 아니게 된다.**

**cron을 요구사항에서 빼는 것이 호스팅을 바꾸는 것보다 싸다.**

---

## 9. 이전 실무

### ① 커스텀 도메인을 먼저 산다

`axubion.ivyro.net`은 아이비 소유 서브도메인이라 이전 시 URL이 반드시 바뀌고, **301 리다이렉트를 걸 수단이 없어 검색 순위와 기존 링크를 전부 잃는다.** 사이트가 커진 뒤에 옮기면 손실이 더 크다.

### ② 도메인 연 비용 (공식 페이지 기준, 2026-07-29 조회)

**.com**

| 등록기관 | 1년차 | 갱신가 | VAT |
|---|---|---|---|
| **Porkbun** | **$11.08** | $11.08 (동일) | 별도 표기 없음 |
| **Cloudflare Registrar** | 원가 청구(마크업 0) | 갱신도 원가 | USD. **실제 금액 확인 필요**(가격 목록 403) |
| 닷홈 | 17,640원(쿠폰) | 24,000원 | **포함** |
| 가비아 | 19,800원(이벤트) | 24,000원 (VAT 별도) = 26,400원 | 정상가는 별도 |
| 후이즈 | **확인 필요** | **확인 필요** (SSO 리다이렉트) | — |

**.kr / .co.kr** — KISA/KRNIC 공식 등록대행자 수수료표(VAT 포함)

| 등록기관 | 신규 | 갱신 |
|---|---|---|
| **호스트센터** | **13,200원** | 13,200원 |
| **가비아** | 23,100원 | 23,100원 |
| 아사달 | 27,500원 | 27,500원 |
| 후이즈 | 28,600원 | 28,600원 |
| 닷홈 | 14,000원(쿠폰) / 정상 20,000원 | **갱신가 확인 필요.** ⚠️ 닷홈은 KRNIC 등록대행자 표에 **없다** — 리셀러 지위 확인 필요 |

출처: [KRNIC 수수료표](https://krnic.or.kr/jsp/popup/agencyFeePop.jsp)

### ③ Cloudflare로는 .kr을 등록할 수 없다

Cloudflare 공식 TLD 정책 목록에 **.kr / .co.kr / .한국이 전부 없고** ccTLD는 "확장 중"이라고만 되어 있다. .kr은 KISA 인증 등록대행자를 통해서만 등록 가능하고 그 목록에 Cloudflare가 없다. **Porkbun도 .kr 미취급.**

출처: [Cloudflare TLD Policies](https://www.cloudflare.com/tld-policies/), [Registrar 지원 TLD](https://developers.cloudflare.com/registrar/top-level-domains/), [KRNIC](https://krnic.or.kr/)

→ **.com이면 Porkbun/Cloudflare로 연 1.5만원 이하, .co.kr을 원하면 국내 등록대행자로 연 1.3~2.3만원.**

### ④ 닷홈을 고를 경우의 함정

무료 Let's Encrypt SSL 조건이 **"닷홈에서 구매한 유료 호스팅과 도메인"** 이다. **도메인을 Porkbun에 싸게 사두면 닷홈 무료 SSL을 못 받는다.** 카페24는 이런 조건이 공식 문서상 없다.

→ **도메인 등록처와 호스팅을 정하는 순서가 얽힌다. 이걸 먼저 결정한다.**

- 카페24 선택 → 도메인은 Porkbun(.com, 연 1.5만원)이 최저가
- 닷홈 선택 → 도메인도 닷홈에서 사야 SSL 무료 (연 2.4만원, 차액 약 9천원 = SSL 비용으로 간주)

### ⑤ 이전 순서

1. 도메인 구매
2. 새 호스팅에 도메인 연결하고 사이트 복제·검증 (**아이비 계약은 유지**)
3. DNS 전환
4. 아이비 해지

아이비 설치비 15,000원은 회수 불가 매몰비용이다.

---

## 10. 계약 전 반드시 서면으로 물을 5가지

공식 문서로 **끝까지 확인 불가**했던 항목들. 카페24 1588-3284 / 닷홈 고객센터에 문의한다.

1. **MariaDB(또는 MySQL) 정확한 마이너 버전은 몇인가?** ("10.x"가 아니라 숫자로)
2. **`curl`, `openssl`, `mysqli`, `mbstring`, `json` 확장이 활성화되어 있는가?**
3. **`max_execution_time`·`memory_limit` 기본값과 `ini_set`/`.htaccess` 변경 허용 여부** — **LLM 응답이 20~30초 걸리면 여기서 죽는다**
4. **PHP에서 `api.deepseek.com`·`api.tosspayments.com`·`accounts.google.com`으로 curl 호출이 허용되는가?** (카페24는 `allow_url_fopen`=Off만 공식 확인됨)
5. **유료 결제가 발생하는 상업적 서비스 운영이 약관상 허용되는가?**

추가로 닷홈이면 **6. WAF가 SQL 문자열이 포함된 POST를 차단하는가?** (§6의 406 사례)

---

## 11. 신청 전 검증 — `probe.php`

파일 하나 올려 브라우저로 열면 5분이다. **확인 후 반드시 삭제한다.**

```php
<?php // probe.php — 확인 후 반드시 삭제
header('Content-Type: text/plain; charset=utf-8');

echo "PHP: ", PHP_VERSION, "\n";
echo "max_execution_time: ", ini_get('max_execution_time'), "\n";
echo "memory_limit: ", ini_get('memory_limit'), "\n";
echo "allow_url_fopen: ", ini_get('allow_url_fopen') ? 'On' : 'Off', "\n\n";

foreach (['mysqli','json','iconv','mbstring','curl','openssl','gd','fileinfo'] as $e)
  echo "$e: ", (extension_loaded($e) ? 'OK' : 'MISSING'), "\n";
echo "\n";

// ini_set 변경 허용 여부
@ini_set('max_execution_time', '60');
echo "ini_set 후 max_execution_time: ", ini_get('max_execution_time'), "\n\n";

// 아웃바운드 — 이게 가장 중요하다
foreach (['https://api.deepseek.com/',
          'https://api.tosspayments.com/',
          'https://accounts.google.com/.well-known/openid-configuration'] as $u) {
  $c = curl_init($u);
  curl_setopt_array($c, [CURLOPT_RETURNTRANSFER=>1, CURLOPT_TIMEOUT=>10,
                         CURLOPT_SSL_VERIFYPEER=>1]);
  $r = curl_exec($c);
  $code = curl_getinfo($c, CURLINFO_HTTP_CODE);
  echo $u, ' → ', ($r !== false ? "OK (HTTP $code, ".strlen($r)."B)"
                                : 'FAIL: '.curl_error($c)), "\n";
}
echo "\n";

// DB
$db = @new mysqli('localhost','ID','PW','DB');
if ($db->connect_error) { echo 'db: FAIL ', $db->connect_error, "\n"; }
else {
  echo 'db server_info: ', $db->server_info, "\n";
  echo 'version(): ', $db->query("SELECT VERSION()")->fetch_row()[0], "\n";
  echo 'sql_mode: ', $db->query("SELECT @@sql_mode")->fetch_row()[0], "\n";
  echo 'collation: ', $db->query("SELECT @@collation_database")->fetch_row()[0], "\n";
  $eng = $db->query("SHOW ENGINES");
  while ($r = $eng->fetch_assoc())
    if ($r['Engine']=='InnoDB') echo 'InnoDB: ', $r['Support'], "\n";
}
```

**보아야 할 것 우선순위**
1. **아웃바운드 curl 3개가 전부 OK인가** — 하나라도 FAIL이면 그 업체는 탈락
2. `curl`·`openssl`·`mysqli` 확장이 있는가
3. **DB `VERSION()` 실제 숫자** — "10.x"의 정체
4. `max_execution_time`이 30 이상이거나 `ini_set`으로 올라가는가
5. `@@collation_database` — 우리 `ex_*` 테이블을 여기 맞춘다
6. `InnoDB: YES`
7. `@@sql_mode`에 `NO_ZERO_DATE`가 있으면 그누보드 설치 SQL(`'0000-00-00 00:00:00'`)이 실패할 수 있다

### WAF 오탐 테스트도 함께

지문에 SQL이 들어가므로 질문 POST가 WAF에 걸릴 수 있다. `probe.php`와 함께 이것도 올려 테스트한다:

```php
<?php // probe_waf.php — POST 폼으로 SQL 문자열을 전송해 406/403이 나는지 확인
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
  echo 'POST 수신 OK, 길이 ', strlen($_POST['q'] ?? ''), "\n";
  exit;
}
?>
<form method="post"><textarea name="q" rows="8" cols="60">
SELECT e.ename, d.dname FROM emp e, dept d
 WHERE e.deptno = d.deptno AND e.sal > 3000
   AND e.ename LIKE 'A%' OR 1=1 UNION ALL SELECT NULL, NULL FROM dual;
</textarea><button>전송</button></form>
```

**`1=1`·`UNION ALL`·`OR`가 들어간 POST가 통과해야 한다.** 406/403이 나면 그 업체에서는 질문 등록이 막힌다.

---

## 12. 확인 불가였던 것

- **후이즈·웹티즌의 전 기술 사양** — 후이즈는 SSO 리다이렉트, 웹티즌은 HTTP 403 봇 차단으로 공식 원문 접근 불가
- **전 업체의 PHP 확장 목록·리소스 한도·상업적 이용 약관** — 공식 문서에 존재하지 않음
- **"국내 공유호스팅이 아웃바운드 curl을 차단한다"는 2025~2026년 실사례** — **찾지 못했다.** 오히려 반대 증거(카페24 공식 fsockopen 권고, 2026-07 Composer 설치 성공 커뮤니티 보고)가 나왔다.
  → **걱정할 지점은 아웃바운드 차단이 아니라 `allow_url_fopen`=Off, 실행시간 제한, 그리고 인바운드 WAF다.**
- 가비아 VPS 요금(공식 페이지 404), 네이버클라우드 Micro 요금(정적 표 없음), Cloudflare .com 실금액(403), Cloudtype MariaDB 선택 가능 버전 목록

---

## 출처

**PHP 지원 버전**
- [php.net Supported Versions](https://www.php.net/supported-versions.php)

**카페24**
- [뉴아우토반 상품](https://hosting.cafe24.com/?controller=new_product_page&page=newautobahn) · [allow_url_fopen 설정](https://cafe24.zendesk.com/hc/ko/articles/18319303326489) · [event_scheduler 불가](https://help.cafe24.com/faq/web-hosting/introduce/setup-management/event-scheduler-setting/) · [cron은 서버호스팅 기능](https://help.cafe24.com/faq/server-hosting/introduce/linux-setup-management/cron-system-scheduling/) · [PHP 버전 변경](https://help.cafe24.com/faq/web-hosting/introduce/new-renewal-change/change_server_environment_php_version/) · [가상서버](https://hosting.cafe24.com/?controller=new_product_page&page=virtual)

**닷홈**
- [요금표](https://www.dothome.co.kr/web/product/price.php) · [SSL](https://www.dothome.co.kr/etc/ssl/price.php) · [도메인](https://www.dothome.co.kr/domain/)

**기타 업체**
- [아이비 상품 사양표](https://www.ivyro.net/html/webht/hosting/?type=secure) · [아이비 매뉴얼](https://www.ivyro.net/html/manual/manual_1.php) · [아이비 과부하 차단](http://notice.ivyro.net/overload/) · [아이비 WAF](http://notice.ivyro.net/modsecurity/waf.html)
- [나우호스팅](https://nowhosting.kr/) · [나우호스팅 웹호스팅](https://nowhosting.kr/bbs/page.php?hid=webhosting)
- [가비아 사양 상세](https://webhosting.gabia.com/service/detail) · [가비아 컨테이너](https://webhosting.gabia.com/container/service/detail) · [가비아 도메인](https://domain.gabia.com/)
- [미리내 공지 uid=975](https://mireene.com/community.php?page_code=board_read&table=notice&uid=975) · [미리내 SSD 상품](https://www.mireene.com/index.php?pid=web_hosting/ssd_hosting/content)
- [iwinv 웹호스팅](https://www.iwinv.kr/account/sharedwebhosting) · [iwinv 서버](https://www.iwinv.kr/server/server) · [iwinv 매뉴얼 43](https://help.iwinv.kr/manual/43)
- [스쿨호스팅 요금](https://www.phps.kr/hosting_price.html) · [후이즈](https://m.whois.co.kr/hosting_webh.php?act=index) · [코리아호스팅](https://koreahosting.co.kr/main.php?menu=s-linux) · [cloudv](https://www.cloudv.kr/)

**도메인**
- [Porkbun](https://porkbun.com/products/domains) · [Cloudflare Registrar](https://www.cloudflare.com/products/registrar/) · [Cloudflare TLD Policies](https://www.cloudflare.com/tld-policies/) · [Cloudflare 지원 TLD](https://developers.cloudflare.com/registrar/top-level-domains/) · [KRNIC 수수료표](https://krnic.or.kr/jsp/popup/agencyFeePop.jsp) · [KRNIC](https://krnic.or.kr/)

**PaaS**
- [Cloudtype Laravel 가이드](https://docs.cloudtype.io/guide/templates/laravel) · [Cloudtype 요금제](https://cloudtype.io/pricing) · [Vercel Runtimes](https://vercel.com/docs/functions/runtimes) · [Netlify 빌드 소프트웨어](https://docs.netlify.com/build/configure-builds/available-software-at-build-time/)

**커뮤니티 (비공식)**
- [sir.kr/questions/565721 — 카페24 Composer 설치 (2026-07)](https://sir.kr/questions/565721) · [sir.kr/questions/564152 — 카페24 외부 웹크론 403 (2026-04)](https://sir.kr/questions/564152) · [sir.kr/boards/free/1705793 — 닷홈 WAF 406 (2025-03)](https://sir.kr/boards/free/1705793) · [wpnews 2022 국내 호스팅 PHP 버전](https://wpnews.co.kr/국내-호스팅업체-신규-설치-시-지원-php-버전-목록-정리/)
