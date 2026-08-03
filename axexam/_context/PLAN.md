# 그누보드5 위에 문제은행 + 질문권 Q&A — 구현 계획

작성 2026-07-29. 함께 읽을 문서:

| 문서 | 내용 |
|---|---|
| **[COST.md](COST.md)** | 운영비·과금 설계. 건당 원가, 검수 노동, PG 고정비, B2B 원가 근거 |
| **[PAYMENT.md](PAYMENT.md)** | 결제. **토스 테스트키로 사업자등록 없이 빌링 성공한 실측** 포함 |
| **[HOSTING.md](HOSTING.md)** | 호스팅 업체 비교·순위. **아이비 탈락 근거**, `probe.php` |
| **[GNUBOARD-FACTS.md](GNUBOARD-FACTS.md)** | 그누보드5 코어 API·확장 지점 검증 사실 (v5.6.34 소스 기준) |

---

## 1. Context

### 현재 상태

`axubion.ivyro.net/sqld/check.html`은 **서버 코드가 0인 정적 사이트**다.

- `scripts/build_check.py`가 `D:\00work\ocr-output-260723\05\*/source/lesson_*.json`을 모아 `06/` 폴더(414MB, 그중 mp4 411MB)를 만들고 FTP로 통째 올린 것
- 데이터는 `window.PROBLEMS`(300문제, 정답·해설 포함) / `window.VIDEOS` / `window.THEORY` / `window.THEORY_HTML` 네 개 전역 JS
- 채점도 브라우저에서 한다
- 6회차 × 50문제 = 300문제. 영상 30개(6회차 × 5파트)

### 붙일 것

- **회원제** — 그누보드5. 질문권 소모를 계정에 붙이기 위한 것
- **질문권 Q&A** — 회원 질문 → 관리자가 검수 화면을 열 때 서버 PHP가 LLM을 `curl`로 호출해 초안 생성 → 관리자가 몰아서 승인 → 노출
- **영상 유튜브 이전** — 무크식 무료 공개. 411MB를 호스팅에서 뺀다

### 이건 LMS가 아니다

진도관리·수강이력·수료증은 스코프에 없다. 그누보드는 CMS(게시판 중심)이고 우리가 만드는 건 **문제은행 + Q&A**다. 서버가 하는 일을 이 둘로 못 박아두는 게 스코프 방어의 핵심이다.

### 대상 자격증 (현 단계)

**SQLD, ADSP, 정보처리기사 필기, 정보처리기사 실기, 컴활** — IT 자격증 계열.

⚠ **실기(정보처리기사 실기, 컴활 실기)는 문제 형태가 객관식이 아니다.** 답안 작성 또는 조작 절차이므로 (a) 정답 판정이 문자열 비교로 안 되고, (b) 부분점수 개념이 필요하고, (c) 프롬프트 재료에 채점 기준이 있어야 한다. **현 파이프라인(`02/`~`05/`)은 객관식 전용이므로 실기는 문제 데이터 제작부터 다시 해야 한다.** 모델 티어 문제가 아니라 콘텐츠 문제다.

### 과금 (확정)

| 항목 | 값 |
|---|---|
| **크레딧 단위** | **원(KRW), 정수.** "건수"가 아니다 |
| **차감** | **질문 1건 = 10원** |
| 실제 LLM 원가 | 0.44~0.78원 (DeepSeek V4-Flash) → 마진 12~23배 |
| 고객 노출 | 차감 단가는 **숨긴다.** "질문 N개 남음"으로 환산 표시 |
| 도메인 혼용 | **하지 않는다.** 자격증군 대분류는 상위에서 분리 |
| 부족 시 | 관리자가 추가 부여 (수동 유연성) |
| 월정액 | 1,100원 / 매월 질문권 50~100개(수치 미확정), **미사용분 이월 없이 소멸** |
| 3개월 결제 | 총 150개를 **월 50개씩 나눠 지급**, 매월 미사용분 소멸 (pool 아님, **월 단위 drip**) |

**크레딧 단위를 "원"으로 잡은 게 핵심이다.** 건수로 잡으면 도메인·모델이 바뀔 때마다 상품과 잔액의 의미가 흔들린다. 원으로 잡으면 차감 단가만 바꾸면 되고 운영비 계산이 그대로 회계와 맞는다. 1,000원 충전 = `lot_qty 1000`, 질문 1건 = `cost 10` → 100건. 표시는 `floor(잔액 / 현재단가)`.

미확정(월 quota 50 vs 100, 무료 공개 범위)은 **전부 설정값이라 지금 결정할 필요가 없다.**

### 프로토타입 단계

사업자등록 전이므로 실결제 대신 **토스 공개 테스트 키로 빌링 플로우를 끝까지 구현**해 데모한다. **실측으로 사업자등록·회원가입 없이 빌링키 발급 + 1,100원 승인이 확인됐다** → [PAYMENT.md](PAYMENT.md) §1.

### B2B 도입 가능성

**wowpass, 유비원평생교육원** 등에서 도입할 가능성이 있다. 설계상 이미 대응되는 것과 새로 필요한 것은 [COST.md](COST.md) §10에 정리했다. 핵심: **검수 노동이 B2B에서 병목이 되므로 계약 전에 검수 주체·SLA·자동승인 여부를 결정해야 한다.**

---

## 2. 스킨도 플러그인도 아니다 — 독립 디렉터리 앱

**형태: `/exam/` 독립 디렉터리 + `include_once('../common.php')`.** 그누보드의 회원·세션·DB만 재사용하고 출력 파이프라인(스킨/테마)은 건드리지 않는다. 코어 파일도 수정하지 않는다.

근거 요약 (상세는 [GNUBOARD-FACTS.md](GNUBOARD-FACTS.md) §1~§3):

1. **`plugin/`은 서드파티 벤더 디렉터리다.** 매니페스트도 스캐너도 활성/비활성 개념도 없다. 배선은 항상 `extend/`에서 한다.
2. **스킨은 그누보드가 이미 가진 화면의 마크업 교체다.** 우리 SPA는 게시판이 아니므로 스킨으로 표현할 대상이 없다.
3. **영카트가 레퍼런스 구현이다.** 같은 레포 최상위 `shop/` 디렉터리, `version.php`에 `G5_YOUNGCART_VER` 병기, `shop/index.php` 첫 줄이 `include_once('./_common.php');`. 우리가 하려는 것과 정확히 같은 구조다.

### 정정 — 훅 API는 실재한다

앞서 "워드프레스식 훅이 없다"고 판단했는데 **틀렸다.** `lib/hook.lib.php`에 있다:

| 함수 | 워드프레스 대응 |
|---|---|
| `add_event($tag, $func, $priority, $args)` | `add_action` |
| `run_event($tag, $arg)` | `do_action` |
| `add_replace($tag, $func, $priority, $args)` | `add_filter` |
| `run_replace($tag, $arg)` | `apply_filters` |

`common.php` L144가 `hook.lib.php`를 include하고 L838이 `extend/`를 로드하므로 **`extend/`에서 훅을 등록할 수 있다.** 다만 공식 훅 목록 문서가 없어서 필요한 태그는 코드에서 `run_event`/`run_replace`를 grep해 찾아야 한다.

우리 설계에 훅이 꼭 필요한 것은 아니지만, **전역 함수 오버라이드가 필요해지면 `add_replace()`가 유일한 수단**이라는 걸 알아둔다.

### 채택 형태

| 만들 것 | 붙는 형태 | 코어 수정 |
|---|---|---|
| 문제풀이 SPA + 질문 UI | **`/exam/check.html` 정적 파일** | 없음 |
| 회원 API (me / qna / credit) | `/exam/api/*.php` + `common.php` include | 없음 |
| 관리자 검수 화면 | **`/adm/exam_*.php`** (고유 접두사) | 없음 |
| 관리자 메뉴 등록 | **`/adm/admin.menu600.exam.php`** ← 파일 추가만 | 없음 |
| 전 페이지 잔여 질문권 전역 | `extend/10_exam.php` | 없음 |
| 회원가입/로그인/소셜로그인 | 그누보드 기본 + `plugin/social/` | 없음 |
| 공지사항 | 그누보드 게시판 | 없음 |

**관리자 페이지를 `adm/` 안에 두는 이유**: `adm/` 밖에 두면 `require './_common.php'`(adm용)를 못 쓰고 `admin.head.php`가 상대 include를 쓰므로 깨질 수 있다. 배포본에 없는 파일명(`exam_*`)이라 업데이트에 안전하다. `admin.menu600` 대역이 비어 있는 것도 확인됐다.

### OIDC 자체 구현은 하지 않는다

**소셜 로그인이 코어 내장이다.** `plugin/social/Hybrid/Providers/`에 `Facebook.php, Google.php, Kakao.php, Naver.php, Payco.php, Twitter.php`가 실제로 있다. `extend/social_login.extend.php`로 배선되고 `g5_member_social_profiles` 테이블도 설치 SQL에 포함돼 있다.

- **구글부터 붙인다** — 표준 OIDC, 심사 없음
- 카카오는 앱 등록·동의항목 심사가 있어 다음
- **애플은 없다** — 필요하면 별도 모듈
- 이메일/비번 가입도 켜둔다. 그누보드가 공짜로 주는 것을 굳이 끄지 않는다

**URL은 `/exam/?pd=sqld`.** 자격증 확장이 확정 로드맵이니 지금 잡는 게 비용 0이다. 기존 `/sqld/`는 301 리다이렉트로 남긴다.

---

## 3. 스코프에서 뺀 것

정답·해설이 이미 공개돼 있고 영상도 무료 개방이므로 아래가 전부 불필요해진다.

| 뺀 것 | 이유 |
|---|---|
| 정답·해설 분리 테이블 | 해설이 무료 개방 → 비밀이 아니다. `ex_problem` 한 테이블에 같이 둔다 |
| 회차별 페이월 / 티저 | 문제·해설 전면 개방 |
| 영상 인증 엔드포인트 | 유튜브 무료 공개 embed |
| 관리자 API 토큰 / 로컬 FastAPI 확장 | 초안 생성이 서버 PHP로 이동. **`app/`과 `services/llm/`은 손대지 않는다** |
| cron | 만료·지급·알림을 전부 조회 시점 처리로 설계 |
| **영카트 / 그누보드 5.7** | 5.7은 master 대비 25커밋 뒤처진 diverged 브랜치(보안 패치 포함). [PAYMENT.md](PAYMENT.md) §3 |
| LMS 기능 일체 | 진도관리·수강이력·수료증. 스코프 밖 |

### 문제는 DB에 넣는다 (결정 변경)

**정정**: 초안에서 "문제를 DB에 넣지 않고 PHP 룩업 배열로 굽는다"고 썼는데 **틀렸다.** 재빌드 마찰을 아끼려다 **문제 데이터를 죽은 자산으로 만드는** 설계였다.

DB에 넣어야 하는 이유:

| 이유 | PHP 배열로는 |
|---|---|
| **B2B 도입** (기관이 문제 추가·편집) | 불가. 로컬 재빌드 + FTP만 |
| **다품목 5종** (SQLD/ADSP/기사 필기·실기/컴활) | 자격증당 300문제면 배열이 1.5MB+. 요청마다 전체 `require` |
| **오타·오답 즉시 수정** | 로컬 재빌드 + FTP 업로드. 급한 수정에 몇 분 |
| **문제 오류 신고 → 수정 루프** | Q&A에서 "이 문제 답이 틀렸다"가 나와도 즉시 못 고친다 |
| **실 정답률 집계** = 문제 품질 지표 | 답안과 조인할 대상이 없다 |
| **문제 본문 검색** | 불가 |
| 실기 문제 (채점 기준·부분점수) | 구조가 복잡해지면 배열로 관리 불가 |

### DB로 가면 되살아나는 것

스코프에서 뺐던 것들이 공짜로 돌아온다. `pr_id` FK가 성립하기 때문이다.

- **`ex_attempt` / `ex_attempt_item` / `ex_wrong`** — 채점 이력·오답노트. 서버 저장
- **`api/grade.php` 서버 채점** — 정답이 공개라도 서버 채점이 낫다. 오답노트·정답률이 공짜로 붙고, 나중에 유료 회차를 만들 때 게이팅 지점이 이미 있고, 클라이언트 채점 코드를 지워 중복이 사라진다
- **실 정답률 20% 미만 = 문제 오류 후보.** `ex_attempt_item`에 `(pr_id, is_ok)` 인덱스를 두면 `GROUP BY pr_id` 한 방이다. `needs_review` 플래그와 교차하면 **검수 우선순위가 자동 생성된다**
- **과목별 정답률 레이더** — subject 버그를 고치면 2과목이 되므로 비로소 의미가 생긴다

### 대신 새로 생기는 비용 2개 — 반드시 다뤄야 한다

**① 웹 수정 vs 재seed 충돌.** 관리자가 웹에서 해설을 고쳤는데 `build_check.py --emit-seed`를 다시 돌리면 덮어써진다. 이게 DB로 가면서 생기는 진짜 비용이다.

→ `ex_problem`에 **`edited_by` / `edited_at`** 컬럼을 둔다. 값이 있으면 **upsert에서 제외**하고 임포트 결과에 "웹 수정본 N건 건너뜀"으로 보고한다. 관리자가 원본으로 되돌리려면 명시적으로 `--force-overwrite` 또는 화면에서 "원본 복원"을 누른다.

`pr_hash`(콘텐츠 md5)도 함께 둬서 **변경분만 업데이트**한다 — 300건 중 3건만 바뀌었으면 3건만 UPDATE되고 나머지는 건드리지 않는다.

**② 임포트 경로.** phpMyAdmin으로 SQL을 매번 붙여넣는 건 실제로 마찰이다. 그래서 **관리자 화면에 임포트를 만든다**:

```
adm/exam_import.php  — problems.json 업로드 → 서버가 upsert → 결과 리포트
                        (신규 N / 갱신 N / 건너뜀 N / 실패 N)
```

`build_check.py --emit-json`으로 `problems.json`을 만들고 FTP로 올린 뒤 버튼 한 번. phpMyAdmin이 필요 없어지고, SSH도 필요 없다. **이게 있으면 "재빌드 마찰"이라는 원래 우려가 사라진다.**

### 단일 진실 원천은 여전히 `02/`다

`D:\00work\ocr-output-260723\02\` (YAML frontmatter + 마크다운)가 원본이고 DB는 배포 사본이다. **다만 웹에서 수정한 것은 DB가 원본이 된다** — 그래서 `edited_by`가 있는 행은 주기적으로 `02/`로 역반영해야 한다. 이 역반영은 수동이어도 되지만, **하지 않으면 언젠가 `02/`가 낡아서 재seed가 수정을 되돌린다.** 문서에 절차로 남긴다.

`data/problems.php` PHP 배열은 **폐기한다.** Q&A 프롬프트 재료 룩업은 PK 조회 1건이라 DB가 충분히 빠르고, 두 곳에 두면 동기 문제가 생긴다.

`problems.js`는 **정적 폴백 전용**(로컬 문제 검수, `file://` 더블클릭)으로만 남는다. 서버에서는 `GET api/problems.php`가 DB에서 읽는다 — 웹에서 고친 문제가 화면에 바로 반영되어야 하므로 이게 필수다.

---

## 4. DB 스키마

`web/sql/schema.sql`. **`g5_member`는 절대 변경하지 않는다** — 확장 필드는 `ex_user_ext`에.

### ⚠ 엔진 InnoDB + 콜레이션 혼용 (실측 반영)

그누보드 코어 테이블은 **MyISAM**이다(`install/gnuboard5.sql`, `adm/sql_write.sql`). MyISAM은 트랜잭션이 없다. 우리 테이블은 **InnoDB**로 직접 만든다.

**콜레이션 — 실측 결과 대응이 필요하다.** 실제 설치본의 DB 콜레이션이 **`utf8mb3_general_ci`** 였다([HOSTING.md](HOSTING.md) probe 결과). utf8mb3는 옛 "utf8"로 **3바이트 문자만** 저장하므로 **이모지·일부 한자가 저장되지 않는다.**

그런데 `ex_*`를 utf8mb4로 만들면 `g5_member`(utf8mb3)와 조인할 때 collation 충돌이 난다.

→ **섞어 쓴다.** 테이블 기본은 `utf8mb4`, **`mb_id` 컬럼만** 그누보드와 동일 콜레이션으로 명시:

```sql
CREATE TABLE ex_qna (
  mb_id VARCHAR(20) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci NOT NULL,
  qa_question MEDIUMTEXT NOT NULL,      -- 테이블 기본 utf8mb4 → 이모지 OK
  ...
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

`mb_id`는 영문+숫자라 utf8mb3로 충분하고, 회원이 쓰는 본문(`qa_question`, `qa_answer`, 문제 텍스트)은 utf8mb4라 이모지가 들어간다.

**아래 모든 `ex_*` 테이블의 `mb_id` 컬럼에 이 지정을 적용한다** — `ex_user_ext`, `ex_entitlement`, `ex_credit_lot`, `ex_credit_ledger`, `ex_order`, `ex_billing`, `ex_qna`, `ex_attempt`, `ex_wrong`, `ex_log`. (아래 DDL은 가독성을 위해 `VARCHAR(20)`으로만 적었다.)

`lg_by`(관리자 mb_id), `edited_by`(관리자 mb_id)도 같은 지정이 필요하다.

```sql
-- 1. 품목 (자격증군)
CREATE TABLE ex_product (
  pd_id      VARCHAR(20)  NOT NULL PRIMARY KEY,  -- 'sqld','adsp','gisa-w','gisa-p','comp'
  pd_name    VARCHAR(100) NOT NULL,
  pd_open    TINYINT      NOT NULL DEFAULT 1,
  tier       VARCHAR(4)   NOT NULL DEFAULT 'T1',
  model_id   VARCHAR(48)  NOT NULL DEFAULT 'deepseek-v4-flash',
  provider   VARCHAR(16)  NOT NULL DEFAULT 'openai_compat',  -- openai_compat | anthropic
  cost_units SMALLINT     NOT NULL DEFAULT 10,     -- 질문 1건당 차감(원)
  cost_cap   DECIMAL(8,4) NOT NULL DEFAULT 3.0,    -- 원가 경고 상한(원)
  pd_config  TEXT NULL,                            -- JSON: 무료 공개 범위 등 미확정 정책값
  pd_sort    INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. 판매 상품
CREATE TABLE ex_plan (
  pl_id     INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  pl_name   VARCHAR(60) NOT NULL,     -- '월 100개 · 1개월'
  pl_price  INT NOT NULL,             -- 1100 (VAT 포함)
  pl_months SMALLINT NOT NULL,        -- 1 / 3 / 12
  pl_quota  INT NOT NULL,             -- 월 지급액(원). 1000 = 질문 100개
  pl_open   TINYINT NOT NULL DEFAULT 1,
  pl_sort   INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2b. 회차 (문제 필터·무료 공개 스위치)
CREATE TABLE ex_round (
  pd_id    VARCHAR(20)  NOT NULL,
  rd_no    SMALLINT     NOT NULL,
  rd_label VARCHAR(100) NOT NULL,   -- '자사 모의고사 01회'
  rd_free  TINYINT NOT NULL DEFAULT 1,   -- 무료 공개 스위치 (현재 전부 1)
  rd_open  TINYINT NOT NULL DEFAULT 1,
  rd_count SMALLINT NOT NULL DEFAULT 0,  -- 문제 수 (임포트가 채움)
  PRIMARY KEY (pd_id, rd_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2c. ★ 문제 — 정답·해설 포함 (공개니까 한 테이블)
CREATE TABLE ex_problem (
  pr_id        INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  pd_id        VARCHAR(20)  NOT NULL,
  rd_no        SMALLINT     NOT NULL,
  pr_key       VARCHAR(40)  NOT NULL,   -- 'm01-1#7' = 기존 keyOf(). 클라이언트 식별자
  bundle       VARCHAR(20)  NOT NULL,   -- 'm01-1'
  pr_no        SMALLINT     NOT NULL,   -- 1..50
  src_id       VARCHAR(20)  NOT NULL,   -- 'm01-07' (02/ 원본 id)
  src_from     VARCHAR(20)  NOT NULL DEFAULT '',  -- derived_from '01-07'
  sj_no        TINYINT      NOT NULL DEFAULT 0,
  sj_name      VARCHAR(100) NOT NULL DEFAULT '',  -- 비정규화(조인 절약)
  difficulty   VARCHAR(4)   NOT NULL DEFAULT '',  -- 상/중/하
  question     MEDIUMTEXT   NOT NULL,
  passage      MEDIUMTEXT   NULL,
  sql_text     MEDIUMTEXT   NULL,
  table_json   TEXT         NULL,       -- {columns:[],rows:[[]]}
  figures_json TEXT         NULL,       -- ["m01-01-super.svg"]
  choices_json TEXT         NOT NULL,   -- ["①문구",...] 순서가 answer_index 기준
  n_choices    TINYINT      NOT NULL DEFAULT 4,
  answer_index TINYINT      NULL,       -- 0-based
  answer_label VARCHAR(8)   NOT NULL DEFAULT '',  -- '②'
  explanation  MEDIUMTEXT   NULL,
  tags_json    TEXT         NULL,
  has_figure   TINYINT NOT NULL DEFAULT 0,
  has_sql      TINYINT NOT NULL DEFAULT 0,
  has_table    TINYINT NOT NULL DEFAULT 0,
  verified     TINYINT NOT NULL DEFAULT 0,   -- 02/*.md frontmatter 복원
  reviewed     TINYINT NOT NULL DEFAULT 0,
  needs_review TINYINT NOT NULL DEFAULT 0,
  pr_open      TINYINT NOT NULL DEFAULT 1,   -- 0 = 숨김 (오류 신고 시 즉시 차단)
  pr_hash      CHAR(32) NOT NULL DEFAULT '', -- 콘텐츠 md5 → 변경분만 UPDATE
  edited_by    VARCHAR(20) NOT NULL DEFAULT '',  -- ★ 웹에서 수정한 관리자. 있으면 재seed 제외
  edited_at    DATETIME NULL,
  updated_at   DATETIME NOT NULL,
  UNIQUE KEY uq_key   (pd_id, pr_key),
  KEY        idx_round(pd_id, rd_no, pr_no),
  KEY        idx_rev  (pd_id, needs_review, pr_open),
  KEY        idx_src  (src_id)
  -- ⚠ FULLTEXT 인덱스는 만들지 않는다. 아래 참조
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. 회원 확장 (g5_member 미변경 원칙)
CREATE TABLE ex_user_ext (
  mb_id      VARCHAR(20) NOT NULL PRIMARY KEY,   -- g5_member.mb_id (논리 FK)
  qna_total  INT NOT NULL DEFAULT 0,
  agree_at   DATETIME NULL,      -- 유료 약관·소멸 조항 동의 시각
  blocked    TINYINT NOT NULL DEFAULT 0,
  memo       VARCHAR(255) NOT NULL DEFAULT '',
  created_at DATETIME NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4. 구독권 = 월 지급의 원천 (drip source)
CREATE TABLE ex_entitlement (
  mb_id          VARCHAR(20) NOT NULL,
  pd_id          VARCHAR(20) NOT NULL DEFAULT '',   -- '' = 전 품목 공용
  monthly_quota  INT NOT NULL,           -- 월 지급액(원)
  months_paid    SMALLINT NOT NULL,
  months_granted SMALLINT NOT NULL DEFAULT 0,
  next_grant_on  DATE NOT NULL,
  started_on     DATE NOT NULL,
  od_id          INT UNSIGNED NOT NULL DEFAULT 0,
  updated_at     DATETIME NOT NULL,
  PRIMARY KEY (mb_id, pd_id),
  KEY idx_grant (next_grant_on)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 5. 질문권 묶음 (지급 1건 = 1 lot). lot_qty/lot_used 단위는 '원'
CREATE TABLE ex_credit_lot (
  lot_id     INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  mb_id      VARCHAR(20) NOT NULL,
  lot_src    VARCHAR(10) NOT NULL DEFAULT 'monthly',  -- monthly|topup|promo|manual|refund
  lot_period CHAR(7)     NOT NULL DEFAULT '',         -- '2026-08' 어느 달 지급분
  lot_qty    INT NOT NULL,                            -- 지급액(원)
  lot_used   INT NOT NULL DEFAULT 0,                  -- ★ 조건부 UPDATE 대상
  lot_expire DATE NOT NULL,                           -- 이 날짜까지 유효(포함)
  lot_exp_logged TINYINT NOT NULL DEFAULT 0,
  lot_note   VARCHAR(120) NOT NULL DEFAULT '',
  created_at DATETIME NOT NULL,
  UNIQUE KEY uq_month (mb_id, lot_src, lot_period),   -- ★ 이중 지급 DB 차원 차단
  KEY idx_bal (mb_id, lot_expire, lot_used)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 6. 원장 (append-only. UPDATE/DELETE 금지 — 정정도 새 행으로)
CREATE TABLE ex_credit_ledger (
  lg_id   BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  mb_id   VARCHAR(20) NOT NULL,
  lot_id  INT UNSIGNED NOT NULL DEFAULT 0,
  lg_type VARCHAR(10) NOT NULL,      -- grant|debit|refund|expire|adjust
  lg_amt  INT NOT NULL,              -- + 지급/환불, - 차감/만료 (원 단위)
  lg_ref  VARCHAR(40) NOT NULL DEFAULT '',  -- 'qna:1234' / 'order:88'  ← 멱등키
  lg_bal  INT NOT NULL DEFAULT 0,    -- 기록 시점 잔액 스냅샷(감사용)
  lg_by   VARCHAR(20) NOT NULL DEFAULT '',
  lg_memo VARCHAR(180) NOT NULL DEFAULT '',
  created_at DATETIME NOT NULL,
  KEY idx_mb (mb_id, created_at), KEY idx_ref (lg_ref)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 7. 주문 (수동 승인 → PG. 스키마 변경 0)
CREATE TABLE ex_order (
  od_id        INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  mb_id        VARCHAR(20) NOT NULL,
  pl_id        INT UNSIGNED NOT NULL,
  od_price     INT NOT NULL,
  od_months    SMALLINT NOT NULL,
  od_quota     INT NOT NULL,
  od_method    VARCHAR(12) NOT NULL DEFAULT 'bank',    -- bank|pg_test|pg|free|coupon
  od_depositor VARCHAR(40) NOT NULL DEFAULT '',
  od_status    VARCHAR(12) NOT NULL DEFAULT 'pending', -- pending|paid|canceled|refunded
  od_pg_tid    VARCHAR(64) NOT NULL DEFAULT '',        -- 토스 paymentKey
  admin_memo   VARCHAR(255) NOT NULL DEFAULT '',
  created_at   DATETIME NOT NULL,
  paid_at      DATETIME NULL,
  KEY idx_mb (mb_id, created_at), KEY idx_st (od_status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 8. 빌링키 (Phase 3) — 상세는 PAYMENT.md §3
CREATE TABLE ex_billing (
  mb_id        VARCHAR(20)  NOT NULL PRIMARY KEY,
  customer_key VARCHAR(64)  NOT NULL,
  billing_key  VARCHAR(255) NOT NULL,   -- ★ 결제수단 그 자체. 유출 = 임의 청구 가능
  card_company VARCHAR(40)  NOT NULL DEFAULT '',
  card_last4   CHAR(4)      NOT NULL DEFAULT '',
  pg           VARCHAR(16)  NOT NULL DEFAULT 'toss',
  is_test      TINYINT      NOT NULL DEFAULT 1,
  created_at   DATETIME NOT NULL, updated_at DATETIME NOT NULL,
  UNIQUE KEY uq_ck (customer_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 9. Q&A
CREATE TABLE ex_qna (
  qa_id     INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  qa_parent INT UNSIGNED NOT NULL DEFAULT 0,   -- 재질문 스레드 (별도 차감)
  mb_id     VARCHAR(20) NOT NULL,
  pd_id     VARCHAR(20) NOT NULL DEFAULT 'sqld',
  kind      VARCHAR(8)  NOT NULL DEFAULT 'qna',   -- qna | grade (논술 채점, Phase 4)
  pr_key    VARCHAR(40) NOT NULL DEFAULT '',      -- 'm01-1#7'. 일반질문은 빈값
  qa_question MEDIUMTEXT NOT NULL,
  qa_chosen TINYINT NOT NULL DEFAULT -1,          -- 질문자가 고른 보기
  qa_status VARCHAR(12) NOT NULL DEFAULT 'pending',
      -- pending → drafting → draft_ready → approved | rejected
  qa_draft  MEDIUMTEXT NULL,     -- ★ LLM 초안. 회원 API에서 절대 SELECT 안 함
  qa_answer MEDIUMTEXT NULL,     -- 관리자 확정 = 공개되는 것
  qa_model  VARCHAR(48) NOT NULL DEFAULT '',
  qa_tok_in    INT NOT NULL DEFAULT 0,
  qa_tok_cache INT NOT NULL DEFAULT 0,   -- 캐시 히트 토큰 (원가 추적)
  qa_tok_out   INT NOT NULL DEFAULT 0,
  qa_cost      DECIMAL(8,4) NOT NULL DEFAULT 0,   -- 실측 원가(원)
  cost_units   SMALLINT NOT NULL DEFAULT 10,      -- 실제 차감액(원). 단가 변경 후에도 환불 정확
  qa_credit_ok TINYINT NOT NULL DEFAULT 0,
  qa_refunded  TINYINT NOT NULL DEFAULT 0,
  qa_public    TINYINT NOT NULL DEFAULT 1,
  qa_draft_at DATETIME NULL, qa_answered_at DATETIME NULL, created_at DATETIME NOT NULL,
  KEY idx_st  (qa_status, created_at),
  KEY idx_mb  (mb_id, created_at),
  KEY idx_pub (pr_key, qa_status, qa_public)   -- 문제별 공개 Q&A = FAQ 조회
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 9b. 채점 이력 (문제가 DB에 있으니 되살아난 것)
CREATE TABLE ex_attempt (
  at_id      INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  mb_id      VARCHAR(20) NOT NULL,
  pd_id      VARCHAR(20) NOT NULL,
  rd_no      SMALLINT NOT NULL,
  at_total   SMALLINT NOT NULL,
  at_correct SMALLINT NOT NULL,
  at_pct     TINYINT  NOT NULL,
  at_sec     INT NOT NULL DEFAULT 0,
  at_filter  VARCHAR(60) NOT NULL DEFAULT '',   -- 과목/난이도 필터 상태
  created_at DATETIME NOT NULL,
  KEY idx_mb (mb_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE ex_attempt_item (
  at_id  INT UNSIGNED NOT NULL,
  pr_id  INT UNSIGNED NOT NULL,
  chosen TINYINT NOT NULL DEFAULT -1,   -- -1 = 미응답
  is_ok  TINYINT NOT NULL DEFAULT 0,
  PRIMARY KEY (at_id, pr_id),
  KEY idx_pr (pr_id, is_ok)             -- ★ 전체 정답률 집계 = 문제 품질 지표
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 9c. 오답노트 (문제별 최신 상태, upsert)
CREATE TABLE ex_wrong (
  mb_id       VARCHAR(20) NOT NULL,
  pr_id       INT UNSIGNED NOT NULL,
  try_cnt     SMALLINT NOT NULL DEFAULT 0,
  wrong_cnt   SMALLINT NOT NULL DEFAULT 0,
  last_chosen TINYINT NOT NULL DEFAULT -1,
  last_ok     TINYINT NOT NULL DEFAULT 0,
  starred     TINYINT NOT NULL DEFAULT 0,
  updated_at  DATETIME NOT NULL,
  PRIMARY KEY (mb_id, pr_id),
  KEY idx_mb (mb_id, last_ok, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 10. 로그 (rate limit + 남용 탐지)
CREATE TABLE ex_log (
  lo_id  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  mb_id  VARCHAR(20) NOT NULL DEFAULT '',
  lo_act VARCHAR(16) NOT NULL,        -- qna|draft|order|login
  lo_ref VARCHAR(40) NOT NULL DEFAULT '',
  lo_ip  VARCHAR(45) NOT NULL DEFAULT '',
  created_at DATETIME NOT NULL,
  KEY idx_mb (mb_id, lo_act, created_at), KEY idx_ip (lo_ip, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

**`qa_draft`와 `qa_answer`를 다른 컬럼으로 둔 것이 핵심 안전장치다.** 회원용 API는 `qa_answer`만 SELECT하고 `qa_draft`는 SELECT 목록에 넣지 않는다. LLM 환각이 검수 없이 공개되는 경로가 구조적으로 존재하지 않는다.

**`cost_units`를 질문 행에도 저장하는 이유**: 차감 단가가 나중에 바뀌어도 과거 질문의 환불액이 정확하다.

**다품목**: 질문권은 품목 공용이다. ADSP 추가 = `ex_product` 1행 + `ex_round` N행 + `build_check.py --pd adsp --emit-json` → 임포트. **PHP 코드 변경 0.**

### 문제 검색 — FULLTEXT 대신 LIKE (MariaDB 제약)

초안에서 `FULLTEXT KEY ft_q (question, passage)`를 넣었는데 **MariaDB에서는 쓸모가 없다.**

MySQL 8.0에는 한국어를 n-gram 단위로 쪼개주는 `ngram` 파서가 있지만 **MariaDB에는 없다.** MariaDB의 기본 FULLTEXT 토크나이저는 공백 기준이라 한국어에서 조사가 붙은 어절("슈퍼타입을", "슈퍼타입의")이 각각 다른 단어로 색인되어 검색이 거의 안 된다. 실측 DB가 MariaDB 10.6.17이므로([HOSTING.md](HOSTING.md)) 이 제약이 그대로 적용된다.

→ **관리자 문제 검색은 `LIKE`로 한다.**

```sql
SELECT pr_id, pr_key, sj_name, question
  FROM ex_problem
 WHERE pd_id = ?
   AND (question LIKE CONCAT('%', ?, '%') OR passage LIKE CONCAT('%', ?, '%'))
 ORDER BY rd_no, pr_no
 LIMIT 50;
```

인덱스를 못 타지만 **문제 수가 자격증 5종 × 300 = 1,500행 수준**이라 풀스캔이 수 ms다. 회원용 기능이 아니라 관리자 검색이므로 호출 빈도도 낮다. 문제가 수만 건이 되면 그때 전용 검색 테이블(형태소 분리 후 색인)을 검토한다.

### 문제 품질 지표 — 문제를 DB에 넣어서 얻는 것

```sql
-- 실 정답률 20% 미만 = 문제 오류 후보. needs_review 와 교차하면 검수 우선순위
SELECT p.pr_key, p.sj_name, p.difficulty, p.needs_review, p.verified,
       COUNT(*) AS tries, ROUND(AVG(i.is_ok)*100, 1) AS pct
  FROM ex_attempt_item i JOIN ex_problem p ON p.pr_id = i.pr_id
 WHERE i.chosen >= 0                      -- 미응답 제외
 GROUP BY i.pr_id HAVING tries >= 10 AND pct < 20
 ORDER BY pct ASC;
```

이게 `adm/exam_problem_list.php`의 기본 정렬이 된다. **문제 오류를 이용자 데이터로 자동 발견하는 경로**이고, PHP 배열 설계에서는 불가능했던 것이다.

`ex_wrong` 기반 오답노트는 회원에게 무료로 준다 — 유료 가치는 Q&A에 있고, 오답노트는 재방문 유도 장치다.

### 커스텀 테이블명은 `extend/`에 등록

`data/dbconfig.php`는 건드리지 않는다. `extend/10_exam.php`에서:

```php
$g5['exam_qna_table']    = G5_TABLE_PREFIX.'exam_qna';
$g5['exam_credit_table'] = G5_TABLE_PREFIX.'exam_credit_lot';
// ...
```

---

## 5. 질문권 로직 — 트랜잭션 없이, cron 없이

### 5-1. 월 지급 (drip) — 조회 시점 정산

```
ex_settle($mb_id):
  while (next_grant_on <= 오늘 AND months_granted < months_paid):
      period = next_grant_on 의 'YYYY-MM'
      INSERT ex_credit_lot (mb_id, lot_src='monthly', lot_period=period,
                            lot_qty=monthly_quota,
                            lot_expire=next_grant_on + 1개월 - 1일)
        └ UNIQUE(mb_id, lot_src, lot_period) 위반이면 무시 (이미 지급됨)
      + ex_credit_ledger (lg_type='grant', lg_amt=+quota)
      months_granted += 1 ;  next_grant_on += 1개월
```

- **미사용분 소멸이 자동이다.** 잔액 계산이 `lot_expire >= CURDATE()`로 만료 lot을 제외하므로 배치가 필요 없다.
- 회원이 두 달 만에 로그인해도 루프가 건너뛴 달을 한 번에 정산한다. 건너뛴 달의 lot은 만료일이 이미 과거라 즉시 소멸되지만 **원장에 흔적이 남아 "왜 없어졌나" 문의에 답할 수 있다.**
- `UNIQUE KEY uq_month`가 **동시 요청으로 인한 이중 지급을 DB 차원에서 막는다.** 이게 이 설계에서 가장 놓치기 쉬운 버그였고 유니크 제약 하나로 해결된다.

### 5-2. 차감 — 조건부 UPDATE. 그누보드 코어가 검증한 패턴

트랜잭션·`FOR UPDATE`·격리수준을 새로 배우지 않아도 된다. **그누보드 자신이 포인트 차감을 이 방식으로 한다** — `insert_use_point()` 주석:

> 매 단계마다 가장 오래된 행 1개를 SELECT한 후 WHERE 절에 사전 검증 조건을 포함한 원자적 UPDATE로 차감한다. **affected_rows로 성공/실패를 판별하고 실패 시 재시도하므로 락 없이 무결성 보장.** (MyISAM/InnoDB 모두 호환, FOR UPDATE 불필요)

```php
// /exam/api/lib/credit.php
function ex_credit_balance($mb_id) {
    $mb = sql_real_escape_string($mb_id);
    $r = sql_fetch("select coalesce(sum(lot_qty - lot_used),0) as bal from ex_credit_lot
                     where mb_id='$mb' and lot_expire >= '".G5_TIME_YMD."'
                       and lot_used < lot_qty");
    return (int)$r['bal'];      // 만료분은 WHERE 절에서 자동 제외 → cron 불필요
}

/* $cost 원 차감. 성공 시 true. 여러 lot에 걸칠 수 있다 */
function ex_credit_debit($mb_id, $cost, $ref, $memo='') {
    $mb = sql_real_escape_string($mb_id);
    $cost = (int)$cost;
    if ($cost <= 0) return false;
    if (ex_credit_balance($mb_id) < $cost) return false;   // 사전 체크(빠른 실패)

    $left = $cost;
    for ($guard = 0; $guard < 20 && $left > 0; $guard++) {
        // FIFO: 먼저 만료되는 lot 부터 소모 (이용자에게 유리)
        $lot = sql_fetch("select lot_id, lot_qty - lot_used as avail from ex_credit_lot
                           where mb_id='$mb' and lot_expire >= '".G5_TIME_YMD."'
                             and lot_used < lot_qty
                           order by lot_expire asc, lot_id asc limit 1");
        if (!$lot) return false;                       // 잔액 소진 (부분 차감 상태 → 아래 주의)
        $take = min($left, (int)$lot['avail']);

        // ★ 원자적 조건부 UPDATE — 동시 요청 중 하나만 성공
        sql_query("update ex_credit_lot set lot_used = lot_used + $take
                    where lot_id = ".(int)$lot['lot_id']."
                      and lot_used + $take <= lot_qty
                      and lot_expire >= '".G5_TIME_YMD."'");
        if (sql_affected_rows() == 1) {
            $left -= $take;
            /* ex_credit_ledger INSERT (lg_type='debit', lg_amt=-$take, lg_ref=$ref) */
        }
        // affected=0 → 경쟁 패배. 루프가 다음 lot(또는 갱신된 같은 lot)을 다시 읽는다
    }
    return $left === 0;
}
```

**동시 요청 시나리오**: 잔액 10원인 회원이 [질문하기]를 연타 → 두 요청이 같은 lot에 `UPDATE ... AND lot_used + 10 <= lot_qty` 실행 → InnoDB가 행을 잠그고 순차 처리 → 첫 번째 `affected=1`, 두 번째 `affected=0` → 두 번째는 다음 lot을 찾고 없으면 실패. **초과 차감이 불가능하다.**

⚠ **여러 lot에 걸친 차감의 부분 실패 주의**: 루프 중간에 실패하면 일부만 차감된 상태가 된다. `$left !== 0`이면 **이미 차감된 만큼을 되돌려야 한다.** 실무적으로는 (a) 차감 전 잔액 사전 체크로 대부분 걸러지고, (b) 되돌림 로직을 `ex_credit_refund($mb, $cost - $left, ...)`로 호출하면 된다. 이 경로를 반드시 테스트한다.

⚠ `sql_affected_rows()` 함수의 정확한 이름은 **확인 필요.** 없으면 `mysqli_affected_rows($g5['connect_db'])`.

⚠ **`sql_escape_string()`이 아니라 `sql_real_escape_string()`을 쓴다.** 전자는 사실상 `addslashes()`다 ([GNUBOARD-FACTS.md](GNUBOARD-FACTS.md) §5).

### 5-3. 질문 등록 순서 (부분 실패 시 손실 방지)

```
1) 품목 설정에서 cost = ex_product.cost_units 조회
2) ex_qna INSERT (qa_status='pending', qa_credit_ok=0, cost_units=$cost)  → qa_id 확보
3) ex_credit_debit($mb, $cost, "qna:$qa_id")                              → true/false
   └ false 이면: ex_qna DELETE → 402 {err:'no_credit'} (충전 안내)
4) ex_qna UPDATE qa_credit_ok=1
```

`4)`가 실패해도 원장에 차감 기록이 남으므로 회계는 정합하다. `qa_credit_ok=0`인 질문은 검수 화면에 **빨간 경고**로 표시해 수동 확인한다. 이 순서가 "질문권은 빠졌는데 질문이 없다"를 원리적으로 막는다.

### 5-4. 반려 환불 — 반드시 있어야 한다

답변을 못 하거나 부적절한 질문이면 관리자가 반려하고 **`ex_qna.cost_units`만큼 돌려준다.** 없으면 "돈 냈는데 답이 없다" 민원이 생긴다.

```php
sql_query("update ex_credit_lot set lot_used = lot_used - $amt
            where lot_id=".(int)$lot_id." and lot_used >= $amt");
if (sql_affected_rows() == 1) { /* ledger lg_type='refund', lg_amt=+$amt */ }
else { /* 원 lot 이 이미 만료 → lot_src='refund' 신규 lot($amt, 만료 +30일) 발급 */ }
```

`ex_qna.qa_refunded`로 중복 환불 방지.

### 5-5. 만료 원장 기록 — lazy

잔액 조회 시 `lot_expire < CURDATE() AND lot_used < lot_qty AND lot_exp_logged=0`인 lot을 발견하면 그 자리에서 `lg_type='expire'` 행을 넣고 `lot_exp_logged=1`. 조회 1회당 최대 몇 건이라 부담 없다.

### 5-6. 정합성 검증 (관리자 화면 상단 1줄)

```sql
SELECT (SELECT COALESCE(SUM(lg_amt),0) FROM ex_credit_ledger) AS ledger_sum,
       (SELECT COALESCE(SUM(lot_qty - lot_used),0) FROM ex_credit_lot) AS lot_avail;
```

원장이 append-only라 언제든 대조 가능하다. 불일치가 나면 `lg_ref`로 추적한다.

**결론: 이 설계에서 cron은 어디에도 필요하지 않다.** 호스팅 요구사항에서 cron을 필수 항목에서 뺀다.

---

## 6. 파일 구조

### 서버 배치도

```
/public_html/                       ← 그누보드5 루트 (설치본. 수정 안 함)
  common.php  bbs/  lib/  plugin/  theme/  skin/  data/
  adm/
    (기존 파일들 — 수정 안 함)
    admin.menu600.exam.php          ← ★ 파일 추가만으로 관리자 메뉴 등록
    exam_index.php                  ← 대시보드 (대기 수, 월 원가 vs 매출)
    exam_qna_list.php               ← ★ 검수 큐 (초안 일괄 생성)
    exam_qna_form.php               ← 승인/반려
    exam_qna_draft.php              ← POST 1건 LLM 호출
    exam_import.php                 ← ★ problems.json 업로드 → upsert (phpMyAdmin 대체)
    exam_problem_list.php           ← ★ 문제 목록. 정답률 낮은 순 정렬, needs_review 필터
    exam_problem_form.php           ← ★ 문제 편집 (저장 시 edited_by/edited_at 기록)
    exam_orders.php                 ← 입금 확인 → 승인
    exam_credit_grant.php           ← 크레딧 수동 지급
    exam_lib/llm.php  exam_lib/prompt.php  exam_lib/problem.php
  extend/
    10_exam.php                     ← 테이블명 등록 + 잔여 질문권 전역
    oauth.extend.php                ← 소셜로그인 설정 (플러그인 설치 시)
  exam/                             ← ★ 독립 디렉터리 앱
    check.html                      ← build 산출물. 정적. common.php include 없음
    problems.js                     ← 정적 폴백 전용 (로컬 검수). 서버에선 API가 이긴다
    videos.js  theory.js  theory_content.js
    assets/{style.css,app.js,ui.js,logo.png}
    figs/*.svg   theory/
    api/
      _boot.php  me.php  credit.php
      problems.php                  ← ★ DB에서 문제 목록 (정답·해설 포함)
      grade.php                     ← ★ 서버 채점 + ex_attempt/ex_wrong 저장
      qna.php  wrong.php
      lib/credit.php  lib/problem.php
    buy.php  mypage.php  wrong.php
    sql/schema.sql  sql/master.sql  sql/.htaccess(deny)
    .htaccess
```

### repo (로컬)

```
D:\00work\260729-new\
  _context\                   ← 이 문서들
    PLAN.md  COST.md  PAYMENT.md  GNUBOARD-FACTS.md
  web\                        ← 서버로 올라갈 PHP/JS 원본 (git 관리)
    exam\...   adm\...   extend\10_exam.php   sql\{schema,master}.sql
  scripts\                    ← 260724-chodangi-mp4 에서 가져올 것
    build_check.py            ← 수정: subject 버그, map_videos, --emit-json
    exam_meta.py              ← 신규: 02 메타 로더
    check_template.html       ← 수정 4곳
  data\youtube_map.json       ← 수동 관리 입력 파일 (빌드가 덮어쓰지 않음)
  docs\
    DEPLOY.md                 ← FTP 업로드 체크리스트
    model-eval.md             ← 자격증별 모델 A/B 결과 기록
```

**`app/` FastAPI와 `services/llm/`은 손대지 않는다.** 초안 생성이 서버로 갔으므로 로컬 확장이 불필요하다. 기존 영상 제작 파이프라인은 그대로.

### `api/_boot.php` (~100줄)

```php
<?php
include_once(dirname(__DIR__, 2) . '/common.php');   // ← 그누보드 세션·DB·$member
header('Content-Type: application/json; charset=utf-8');
header('X-Content-Type-Options: nosniff');
header('Cache-Control: private, no-store');

function ex_out($a)        { echo json_encode($a, JSON_UNESCAPED_UNICODE); exit; }
function ex_fail($m,$c=400){ http_response_code($c); ex_out(array('ok'=>0,'err'=>$m)); }
function ex_mb()           { global $member; return $member['mb_id']; }   // 비로그인은 ''
function ex_admin()        { global $member; return $member['mb_id'] && $member['mb_level'] >= 10; }
function ex_csrf()         { /* 세션에 없으면 bin2hex(random_bytes(16)) 발급 */ }
function ex_csrf_ok()      { /* X-Exam-Csrf 헤더를 hash_equals 로 비교 */ }
function ex_rate($act,$max,$sec) { /* ex_log COUNT */ }
function ex_log($act,$ref='')    { /* ex_log INSERT */ }
function ex_ext($mb_id)          { /* ex_user_ext 없으면 INSERT (최초 접속 자동 생성) */ }
```

⚠ **비로그인도 `$member['mb_level']`이 1이다.** 로그인 판정은 반드시 `if ($member['mb_id'])`로 한다.

⚠ **`check_token()`을 JSON API에서 쓰지 않는다.** 실패 시 `alert()`(JS)를 출력하므로 응답에 HTML이 섞인다. 자체 CSRF(`ex_csrf_ok()`)를 쓰고, 보조로 `check_request_origin()`을 병행한다.

### 회원 API 6개

| 엔드포인트 | 동작 |
|---|---|
| `GET api/problems.php?pd=&round=` | **DB에서** 문제 목록. `WHERE pr_open=1` (오류 신고된 문제 숨김). 정답·해설 포함(공개). `rounds[]`·`subjects[]` 동봉. **ETag** = `md5(pd\|rd\|MAX(updated_at))` → `If-None-Match` 시 304 |
| `POST api/grade.php` | 답안 배열 → 서버 채점 → `{score, results[]}`. 로그인 회원이면 `ex_attempt` + `ex_attempt_item` INSERT, `ex_wrong` upsert. **비로그인도 채점은 되고 기록만 안 남는다**(회원가입 유도) |
| `GET api/me.php` | `ex_settle()` 먼저 실행 → `{ok:1, login:1, mb_id, nick, bal:870, count:87, unit:10, lots:[...], csrf}` |
| `POST api/qna.php` | 로그인 → CSRF → `ex_rate('qna',20,86400)` → **5-3 절차** → `{ok:1, qa_id, bal, count}`. 잔액 부족 `402 {err:'no_credit'}` |
| `GET api/qna.php?mine=1` / `?keys=a,b,c` | `mine=1`: 내 질문 전체(상태 포함). `keys=`: 해당 문제들의 `approved AND qa_public=1` 답변만. **두 경우 모두 `qa_draft`를 SELECT하지 않는다** |
| `GET api/credit.php` / `api/wrong.php` | 원장 내역 / 오답노트. 만료 lazy 기록은 `credit.php`에서 |

`count = floor(bal / unit)`. **화면에는 `count`만 쓴다** — 단가를 노출하지 않는다 ([COST.md](COST.md) §8).

**`grade.php`가 답안 화이트리스트를 검증한다**: 클라이언트가 보낸 키를 그 회차에 속한 `pr_key`로 필터하고, `pr_key` 형식을 정규식(`/^m\d{2}-\d#\d{1,3}$/`)으로 검증한 뒤 `IN (...)`에 바인딩한다. 임의 키를 넣어 다른 회차 정답을 긁는 걸 막는다.

**gzip 필수**: `.htaccess`에 `AddOutputFilterByType DEFLATE application/json`. 50문제 JSON이 약 50KB → 12KB.

### 임포트 — phpMyAdmin을 쓰지 않는다

`adm/exam_import.php`: `problems.json` 업로드 → 서버가 upsert → 리포트.

```
[임포트 결과]
신규     12건
갱신      3건   (pr_hash 변경분만)
건너뜀    2건   ← ★ edited_by 가 있는 웹 수정본. 덮어쓰지 않았다
실패      0건
회차 갱신 ex_round.rd_count 6행
```

upsert 규칙:
```sql
INSERT INTO ex_problem (...) VALUES (...)
ON DUPLICATE KEY UPDATE
  question=IF(edited_by='', VALUES(question), question),   -- 웹 수정본 보호
  ...  -- 나머지 컬럼 동일 패턴
  pr_hash=IF(edited_by='', VALUES(pr_hash), pr_hash),
  updated_at=IF(edited_by='', VALUES(updated_at), updated_at);
```

**`pr_id`는 절대 바뀌면 안 된다** — `ex_attempt_item`/`ex_wrong`이 참조한다. `UNIQUE KEY (pd_id, pr_key)`가 upsert 축이고 **DELETE + INSERT는 금지**다. seed 파일과 임포트 코드에 주석으로 경고를 박는다.

**"원본 복원"** 버튼: `edited_by`를 비우고 다시 임포트하면 `02/` 원본으로 돌아간다. 관리자가 명시적으로 눌러야 한다.

⚠ **업로드 파일 크기 제한** — 자격증 5종 × 300문제면 JSON이 수 MB다. `upload_max_filesize`/`post_max_size` 확인 필요. 넘으면 품목별로 쪼개 올린다(`--emit-json --pd sqld`).

Rate limit 근거: 하루 20건은 정상 학습자가 못 넘는 선이고, 크레딧을 가진 회원이 스크립트로 1,000건을 밀어 LLM 원가를 태우는 것을 막는다.

### 관리자 검수 화면 — `max_execution_time` 회피

```
┌─ 좌 260px ────────┬─ 우 ──────────────────────────────────────┐
│ 대기 12 / 초안 5  │ [문제 1회 7번 · SQL 기본 및 활용        ] │
│ ───────────────── │ [문제 원문 · 보기 · 정답 ② · 공식 해설  ] │
│ ▸ #123 김(m01-1#7)│ [수강생 질문 / 고른 보기 ③              ] │
│ ▸ #124 이 (일반)  │ ───────────────────────────────────────── │
│                   │ [초안 textarea — 편집 가능              ] │
│ [대기 초안 생성]  │ [재생성][승인·공개][승인·비공개][반려]   │
│                   │ 토큰 in 2,140(캐시 1,980) out 812 = 0.4원│
└───────────────────┴───────────────────────────────────────────┘
```

**초안 생성 루프 — JS가 1건씩 직렬 호출한다:**

```js
for (const id of pendingIds) {                  // ★ 직렬. 병렬 금지
  setStat(id, '생성중…');
  const r = await fetch('exam_qna_draft.php', {method:'POST',
    headers:{'Content-Type':'application/x-www-form-urlencoded','X-Exam-Csrf':CSRF},
    body:'qa_id='+id});
  const j = await r.json();
  setStat(id, j.ok ? '초안 완료' : ('실패: '+j.err));
}
```

- 요청 1개 = LLM 1회 = 3~8초 → `max_execution_time 30`에 여유롭게 들어간다. 12건이어도 요청 12개로 쪼개지니 타임아웃이 날 수 없다.
- **병렬로 던지면 안 된다.** 공유호스팅의 PHP 동시 프로세스 제한에 걸리고 rate limit도 문제가 된다.
- 진행률이 화면에 보여서 관리자가 상황을 안다.

`adm/exam_qna_draft.php` 핵심:
1. **선점을 조건부 UPDATE로** (`pending → drafting`, `affected != 1`이면 "이미 처리 중")
2. `ex_problem` 에서 `pr_key` 로 프롬프트 재료 조회 (PK 조회 1건)
3. `ex_llm_chat()` — curl, **`CURLOPT_TIMEOUT=25`** (반드시 `max_execution_time`보다 작게)
4. 실패 시 `pending`으로 되돌림
5. 성공 시 `draft_ready` + 토큰·원가 기록. `qa_cost > ex_product.cost_cap`이면 경고 플래그

`adm/exam_qna_form.php`: `status='approved'`인데 `answer`가 비면 **422 거부**(초안 그대로 공개되는 사고 방지). `rejected`면 환불 + `qa_refunded=1`. 처리 후 **그누보드 쪽지(`g5_memo`)를 자동 발송**해 회원이 답변을 알아채게 한다 — 그누보드 기능 재사용이라 cron이 불필요하다.

**검수 속도 최적화 (COST.md §3의 1순위 대책)**: 키보드 단축키(승인 `Enter`, 다음 `J`, 반려 `R`), 초안 그대로 승인 원클릭, `[검수필요]` 초안 노란 배경 강조, 같은 문제 반복 질문 묶어 표시.

API 키는 웹루트 밖 `/home/<user>/private/exam_secret.php`. 불가능하면 `exam/data/secret.php` + `.htaccess deny` + `<?php exit;` 가드.

### `adm/exam_lib/llm.php` — provider 2분기

DeepSeek/MiMo는 OpenAI 호환이지만 **Anthropic은 자체 API다.** 하나로 통일하려 하지 말고 분기 2개로 짠다:

```php
function ex_llm_chat($pd, $messages) {
    switch ($pd['provider']) {
        case 'anthropic':      return ex_llm_anthropic($pd, $messages);
        case 'openai_compat':
        default:               return ex_llm_openai_compat($pd, $messages);
    }
}
```

`ex_product.provider` + `model_id`가 설정값이므로 티어 전환이 DB 값 변경으로 끝난다.

**공통 필수 설정**: `max_tokens: 1200` (원가 폭주 방어), `CURLOPT_TIMEOUT: 25`, 응답 `usage` 파싱 → `qa_tok_in`/`qa_tok_cache`/`qa_tok_out`/`qa_cost`.

**모델 ID 주의**:
- DeepSeek: **`deepseek-v4-flash`**. 레거시 `deepseek-chat`/`deepseek-reasoner`는 2026-07-24 폐지
- Claude: `claude-haiku-4-5`, `claude-sonnet-5`, `claude-opus-5`. **날짜 접미사 금지.** Opus 5는 사고가 기본 ON이라 `max_tokens`가 사고+응답을 합쳐 제한하므로 여유를 둬야 한다

### 프롬프트 — 캐싱 순서가 전부다

`[완전 고정] → [문제별 고정] → [가변]` 순으로 쌓아야 프리픽스 캐시가 걸린다.

```php
// adm/exam_lib/prompt.php
return array(
  array('role'=>'system', 'content'=> EXAM_SYSTEM_RULES),          // ① 항상 캐시 히트
  array('role'=>'user',   'content'=>                              // ② 같은 문제 2번째부터 히트
    "[문제 {$pr['rd']}회 {$pr['no']}번 · {$pr['sj']}]\n{$pr['q']}\n\n"
   ."[보기]\n".ex_numbered($pr['c'])."\n\n[정답] ".$pr['an']."\n\n[공식 해설]\n".$pr['ex']),
  array('role'=>'user',   'content'=>                              // ③ 가변
    ($qa['qa_chosen'] >= 0 ? "수강생이 고른 보기: ".($qa['qa_chosen']+1)."번\n\n" : "")
   ."수강생 질문:\n".$qa['qa_question']),
);
```

`EXAM_SYSTEM_RULES` — 환각 억제가 최우선:

```
너는 [자격증명] 조교다. 아래 규칙을 반드시 지켜라.
1. 제공된 문제·정답·공식 해설의 범위를 벗어난 사실을 만들지 마라.
2. 공식 해설과 다른 결론이 나오면 답하지 말고 첫 줄에 "[검수필요]" 를 써라.
3. 수강생이 고른 오답이 왜 틀렸는지를 중심으로 설명해라.
4. 400자 이내. 마크다운은 **강조**, `코드`, - 목록만. 표·이미지 금지.
5. 시험 범위 밖 심화 내용은 "시험 범위 외"라고 명시하고 한 문장으로만.
```

**규칙 2(결론 불일치 시 자진 신고)가 실전에서 가장 잘 듣는다.** 검수 시간을 크게 줄여주는 장치이기도 하다 — `[검수필요]`가 없는 초안은 스캔만 하고 넘어갈 수 있다.

프롬프트를 `config/qna_prompt.yaml` 같은 데이터 파일로 빼면 자격증별 조교 페르소나를 코드 수정 없이 바꿀 수 있다.

### `extend/10_exam.php`

테이블명 등록 + 그누보드 페이지(게시판/마이페이지)에서도 잔여 질문권을 보여주기 위한 전역. **60초 세션 캐시**를 둔다(표시 전용이라 안전하다. 실제 차감 판정은 `api/lib/credit.php`가 DB를 직접 조회한다).

> 성능 주의: `extend/`는 **모든 그누보드 페이지에서** 실행된다. 세션 캐시가 있어 쿼리는 사실상 안 나가지만 로직을 여기에 더 넣지 않는다.

파일명 `10_exam.php` — `extend/`는 `.php` 전체를 `natsort` 순서로 include하므로 숫자 접두어로 로드 순서를 제어한다.

---

## 7. 기존 파일 수정

### `scripts/exam_meta.py` (신규, ~50줄) — subject 버그의 해법

```python
def load_meta(book: Path) -> dict[str, dict]:
    """'m01-07' → {subject, subject_no, verified, reviewed, needs_review, derived_from}"""
    idx = json.loads((book / '02' / '_index.json').read_text('utf-8'))
    out = {it['id']: dict(it) for it in idx['items']}
    for md in (book / '02').glob('m*.md'):        # verified/needs_review 는 여기에만 있다
        parts = md.read_text('utf-8').split('---', 2)
        if len(parts) >= 3:
            fm = yaml.safe_load(parts[1]) or {}
            if fm.get('id'):
                out.setdefault(fm['id'], {}).update({k: fm.get(k) for k in
                    ('subject','subject_no','verified','reviewed','needs_review','authored_by')})
    return out
```

`pyyaml>=6.0`이 `requirements.txt:8`에 이미 있어 추가 의존성이 없다.

### `scripts/build_check.py` 수정 3곳

**(a) `subject` 폴백 버그 픽스 (`:93-101`).** `b.get("subject") or subj`가 300개 전부 `"SQLD"`로 채운다 — lesson JSON의 문제 블록에 `subject` 키가 **아예 없기** 때문이다. 그래서 화면 과목 필터(`check_template.html:216`)에 선택지가 하나뿐이고 무의미하다. 진짜 과목은 `02/_index.json`에만 있고 **2종**이다(`데이터 모델링의 이해` 60개, `SQL 기본 및 활용` 240개).

조인 키는 결정적이고 **300/300 무손실 매칭이 확인됐다**:

```python
src_id = f"m{rn:02d}-{int(b['number']):02d}"     # 'm01-07'
meta   = META.get(src_id, {})
...
"subject":      meta.get('subject') or '',       # ← 'SQLD' 폴백 제거
"subject_no":   meta.get('subject_no') or 0,
"verified":     bool(meta.get('verified')),
"needs_review": bool(meta.get('needs_review')),
```

`--strict-meta`: 메타 미발견 문제가 하나라도 있으면 빌드 실패(조용한 데이터 손실 방지). 현재 300/300이므로 바로 켠다.

**이 수정만으로 정적 빌드에서도 과목 필터가 즉시 정상화된다** — 서버 작업과 무관하게 먼저 해도 된다.

**(b) `copy_videos()` → `map_videos()` (`:119-142`).** mp4 복사와 `--video-rounds` 옵션을 **완전히 제거**한다. `data/youtube_map.json`을 읽어 `{label, part, provider, id, sec}`를 낸다. 배포물 414MB → 2.67MB.

`{provider, id}` 추상화는 유지한다. 유튜브 정책 문제가 생기면 `provider`를 `vimeo`/`file`로 바꾸고 `openVid()`에 분기 한 줄이면 끝난다. 비용이 거의 0이므로 지금 해둔다.

`data/youtube_map.json`은 **수동 관리 입력 파일이고 빌드가 절대 덮어쓰지 않는다**(`--init-youtube-map`으로 빈 골격만 1회 생성). 30줄이라 JSON 하나로 충분하다.

**(c) `--emit-json`** — `problems.json` 생성. `adm/exam_import.php`가 업로드받아 upsert한다.

```json
{
  "pd_id": "sqld",
  "generated_at": "2026-07-29T18:00:00+09:00",
  "rounds": [{"rd_no":1,"rd_label":"자사 모의고사 01회","rd_count":50}, ...],
  "subjects": [{"sj_no":1,"sj_name":"데이터 모델링의 이해"}, {"sj_no":2,"sj_name":"SQL 기본 및 활용"}],
  "problems": [
    {"pr_key":"m01-1#1","bundle":"m01-1","rd_no":1,"pr_no":1,"src_id":"m01-01",
     "sj_no":1,"sj_name":"데이터 모델링의 이해","difficulty":"중",
     "question":"...","passage":"","sql_text":"","table_json":null,
     "figures_json":["m01-01-super.svg"],
     "choices_json":["①문구","②문구","③문구","④문구"],
     "answer_index":1,"answer_label":"②","explanation":"...","tags_json":["슈퍼타입"],
     "verified":true,"reviewed":false,"needs_review":true,
     "pr_hash":"a1b2c3..."}
  ]
}
```

`pr_hash`는 콘텐츠(question + passage + sql + choices + answer_index + explanation) md5. 임포트가 이걸로 변경분만 UPDATE한다.

`--emit-php`(PHP 룩업 배열)는 **폐기했다.** 문제가 DB에 있으므로 불필요하다.

새 옵션:
```
python scripts/build_check.py                                # 정적 폴백 빌드 (mp4 복사만 사라짐)
python scripts/build_check.py --emit-json                    # problems.json → 임포트용
python scripts/build_check.py --emit-json --pd sqld          # 품목별 분할 (업로드 상한 대비)
python scripts/build_check.py --api-base ./api/              # check.html 에 EXAM_API 주입
python scripts/build_check.py --init-youtube-map             # 골격 생성 (1회)
```

### `scripts/check_template.html` — 개조 5곳 (문제 DB화로 1곳 늘었다)

**정정**: 초안에서 "개조 4곳뿐, `window.PROBLEMS` 그대로"라고 썼는데, 문제를 DB에 넣기로 하면서 **데이터 소스 추상화가 추가로 필요하다.** 웹에서 고친 문제가 화면에 반영되어야 하므로 `problems.js`를 그대로 쓸 수 없다.

**여전히 무수정인 것**: 마크업·CSS·마크다운 렌더러(`md`, `mdb`, `mdTable`, `sqlRun` — 약 60줄)·이론 Shadow DOM(`:330`). 이게 이 프로젝트에서 가장 값진 자산이다.

**(0) 데이터 소스 추상화 (신규)** — `:166-168`의 전역 4개를 함수로 감싼다.

```js
const API = window.EXAM_API || "";
const DS = API ? ApiDS : StaticDS;
// 공통 인터페이스
//   DS.rounds()              → [{no, label, count, free}]
//   DS.problems(round)       → {problems:[], subjects:[]}
//   DS.grade(round, answers) → {score:{correct,total,pct}, results:[{key,ok,chosen,answer_index,explanation}]}
//   DS.video(bundle)         → {provider, id, label}
//   DS.me()                  → {login, nick, count, csrf}
```

- `StaticDS` = 기존 `window.PROBLEMS` 읽기 + **클라이언트 채점**(현 `grade()` 로직 그대로 이동). `file://` 로컬 검수용
- `ApiDS` = `fetch('api/problems.php')` + `fetch('api/grade.php')`

**`API`가 비면 `StaticDS`가 선택되어 기존 정적 빌드가 아무 수정 없이 그대로 동작한다.** 마크업 1개, JS 1개, 소스만 스왑. 정적 폴백을 공짜로 유지하는 방법이다.

**(1) 채점을 서버로** (`:293-304`) — `grade()`가 `await DS.grade(round, answers)`를 부르고 응답의 `results[]`로 `.correct`/`.wrong` 클래스와 해설을 주입한다. 해설은 `render()`에서 미리 삽입하지 않고 `<div class="expl"></div>` 빈 껍데기로 두었다가 채점 응답으로 채운다.

`reveal()`("정답 보기")은 `DS.grade(round, {})`(전 문항 미응답 채점)로 통일한다.

**(2) `openVid()` 유튜브 전환** (`:154`, `:320`, `:344`, `:347`) — `<video src>`를 iframe embed로. `:154`의 `<video id="vplayer">`를 빈 `<div class="box">`로 바꾸고 `closeVid()`에서 `innerHTML=""`로 재생을 멈춘다.

**(1) `openVid()` 유튜브 전환** (`:154`, `:320`, `:344`, `:347`) — `<video src>`를 iframe embed로. `:154`의 `<video id="vplayer">`를 빈 `<div class="box">`로 바꾸고 `closeVid()`에서 `innerHTML=""`로 재생을 멈춘다.

**(3) 헤더 계정칸 + 잔여 질문권** (신규 `#acct`)

```js
const API = window.EXAM_API || "";     // 정적 로컬 빌드에서는 빈 값
async function loadMe(){
  if(!API) return;                     // file:// 이면 그냥 넘어간다
  try{ ME = await (await fetch(API+"me.php",{credentials:"same-origin"})).json(); }catch(e){}
  renderAcct();                        // "질문 87개 남음" — 단가는 표시하지 않는다
}
```

**`API`가 비면 계정칸과 질문 버튼이 자동으로 사라진다.** 즉 기존 정적 빌드(`file://` 더블클릭 = 로컬 문제 검수용)가 **아무 수정 없이 그대로 동작한다.** 이게 템플릿 이중 관리를 피하는 방법이다 — 마크업 1개, JS 1개, 동작만 환경에 따라 갈린다. `build_check.py`가 `--api-base ./api/`로 빌드할 때 `<script>window.EXAM_API="./api/";</script>` 한 줄을 주입한다.

⚠ **그누보드 head를 쓰는 페이지에서는 jQuery 충돌 주의.** `head.sub.php`가 jQuery 1.12.4 + migrate 1.4.1을 무조건 로드한다. `check.html`은 그누보드 head를 include하지 않으므로 문제없지만, `mypage.php`/`buy.php`는 include하므로 거기서 최신 jQuery를 다시 로드하면 안 된다.

**(4) 문제 카드에 `[질문하기]` + 공개 Q&A** (`render()` `:262-275` 반환 문자열 끝에 추가)

- **질문 폼을 열기 전에 이 문제의 기존 공개 답변을 먼저 보여주고 "이걸로 해결됐어요" 버튼을 둔다.** 누르면 질문권 차감 0. **[COST.md](COST.md) §3의 검수 병목 대책 1번이 여기서 구현된다** — 효과가 가장 크다.
- `askOpen(key)` → 모달: 질문 textarea + 고른 보기 자동 첨부 + **"질문권 1개가 사용됩니다 (잔여 N개)"** 명시 → `POST api/qna.php`. `402` → 충전 안내, `429` → 토스트(기존 `toast()` 재사용)
- 렌더 후 `GET api/qna.php?keys=m01-1%231,m01-1%232,...` **한 번으로 화면에 보이는 문제들의 공개 Q&A를 일괄 조회**해 채운다(문제당 1요청은 안 된다)

**(5) 부트를 async로** (`:352-359` IIFE) — `loadMe()` + `DS.rounds()` + `DS.problems()`를 `await`한다. 첫 렌더가 fetch 1~2회 뒤로 밀리므로 로딩 스켈레톤이나 "불러오는 중…" 표시를 넣는다.

또 하나 추가할 것: **문제 오류 신고 버튼.** 문제 카드에 작게 두고, 누르면 `pr_key`와 사유를 보낸다. 관리자가 확인해 `pr_open=0`으로 즉시 숨기거나 `needs_review=1`을 세운다. 질문권을 소모하지 않는다 — 오류 신고는 **우리에게 이득**이므로 대가를 받으면 안 된다.

**`check.html`을 `index.php`로 바꾸지 않는 이유**: `api/*.php` fetch로 데이터를 받으면 **정적 파일 그대로 유지**할 수 있다. `common.php` include가 없으니 그누보드 출력 파이프라인·jQuery 1.12.4·모바일 분기와 완전히 무관해지고 정적 폴백이 공짜로 유지된다.

### 폰트 2MB → **Phase 1 필수** (정정)

`assets/fonts/PretendardVariable.woff2` = 2.06MB로 `assets/` 전체의 98%다.

초안에서 "P2 개선 항목"이라고 썼는데 **틀렸다.** 실제 계약한 카페24 뉴아우토반 일반형의 **트래픽이 4,000MB**다:

```
4,000MB ÷ 2.06MB ≈ 신규 방문 1,940명에 월 트래픽 소진
```

마이캐쉬 잔액 0원 + 트래픽 자동 리셋 꺼짐 상태이므로 **초과하면 사이트가 멈춘다.**

→ **`shell.html`에 CDN `<link>` 한 줄로 처리한다.** 배포물이 2.67MB → 약 600KB가 되고 방문당 2MB가 0이 된다. Phase 1의 빌드 단계에서 함께 한다.

```html
<link rel="stylesheet"
      href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css">
```

빌드에서 `_context/present/assets/fonts/`를 복사 대상에서 제외하고, `assets/style.css`의 `@font-face` 블록을 제거한다.

⚠ 4,000MB가 월 기준인지 일 기준인지는 **확인 필요**([HOSTING.md](HOSTING.md) 신청 완료 절). 일 기준이면 여유가 크지만 어느 쪽이든 CDN이 맞다.

---

## 8. 로그인·마이페이지 — 하이브리드

| 화면 | 방식 | 근거 |
|---|---|---|
| 회원가입 / 로그인 / 비번찾기 / 정보수정 / 탈퇴 / 약관 | **그누보드 기본** | **법적 문구·보안·메일 흐름이 완성품**이다. 여기서 아끼는 시간이 가장 크다. 디자인은 테마 CSS 변수만 우리 팔레트로 덮어 색만 맞춘다 — 마크업 미수정 |
| 소셜 로그인 | **`plugin/social/` 코어 내장** | 구글/카카오/네이버/페이스북/트위터/페이코. 애플만 없음 |
| 마이페이지(잔액·내 질문·원장) | **커스텀** `/exam/mypage.php` | 그누보드에 대응 개념이 없다 |
| 구매·입금안내 | **커스텀** `/exam/buy.php` | 동일 |
| 공지사항 | **그누보드 게시판** | 공짜로 얻는 것 그대로 |
| 관리자 회원관리 | **그누보드 `/adm/`** | 완성품 |
| 관리자 Q&A 검수·주문 승인 | **커스텀** `/adm/exam_*.php` | `mb_level>=10` + `auth_check_menu()` |

**Q&A는 그누보드 게시판을 쓰지 않는다.** 근거는 [GNUBOARD-FACTS.md](GNUBOARD-FACTS.md) §8 — LLM 초안이 `wr_1`~`wr_10`(255바이트)에 안 들어가고, 상태 컬럼에 인덱스가 없고, 승인 전 비노출을 만들려면 목록/검색/최신글/RSS를 전부 무력화해야 하고, 비밀글이 "내 것만 본다"를 절반만 만족하고, `g5_write_*`가 MyISAM이다.

로그인 리다이렉트: `/bbs/login.php?url=` + `urlencode('/exam/?pd=sqld')`. 코어 수정 없음.

---

## 9. 호스팅 요구사항

배포물이 414MB → 2.67MB(폰트 CDN 시 약 600KB)로 줄어 용량·트래픽 요구가 사실상 사라졌다. **결정 요인은 PHP/DB 버전과 outbound curl뿐이다.**

**업체 선정은 [HOSTING.md](HOSTING.md)에 별도 정리했다.** 결론: **1순위 카페24 뉴아우토반 일반형(1,500원 VAT포함), 2순위 닷홈 1.5G(900원). 아이비호스팅은 PHP 상한 8.0(보안지원 종료)으로 탈락.**

### ⚠ 정정 — PHP 8.0·8.1은 이미 보안 지원이 끝났다

php.net 공식 지원 버전 표에 **8.0·8.1이 등재되어 있지 않다.** 보안 지원 최소는 **8.2(2026-12-31까지)**, 8.3은 2027-12-31, 8.4는 2028-12-31.

→ 앞서 "PHP 8.1 또는 8.2"라고 쓴 건 틀렸다. **최소 8.2, 신규 구축은 8.3 이상으로 간다** (8.2도 5개월 뒤 EOL).

### 필수 (하나라도 안 되면 탈락)

| # | 항목 | 요구 | 왜 |
|---|---|---|---|
| 1 | **PHP** | **8.3 이상 권장 (최소 8.2)** | 8.0/8.1은 보안 지원 종료. 그누보드5.6.x는 코드상 최소 5.2.17이고 PHP 8 전용 분기가 실재하므로 8.4도 무리 없다 |
| 2 | **MariaDB / MySQL** | **MariaDB 10.6+ 권장** | ⚠ 공식 설치 SQL이 `'0000-00-00 00:00:00'`을 쓴다 → MySQL 5.7/8.0 기본 `sql_mode`(`NO_ZERO_DATE`)에서 문제 소지. **MariaDB가 실무상 안전** |
| 3 | **InnoDB 사용 가능** | 필수 | §5 조건부 UPDATE의 행 잠금. 코어는 MyISAM이지만 우리 테이블은 InnoDB로 만든다 |
| 4 | **외부 outbound `curl`** | **필수** | 막히면 서버사이드 LLM 호출 불가. ⚠ **카페24는 `allow_url_fopen`=Off가 공식**이므로 `file_get_contents()`가 아니라 **반드시 curl로 쓴다.** 아웃바운드 차단 실사례는 조사에서 찾지 못했고 오히려 반대 증거가 나왔다 |
| 4b | **인바운드 WAF 오탐** | **테스트 필수** | 지문에 SQL이 들어가므로 질문 POST가 SQL 인젝션으로 오탐될 수 있다. 닷홈에 정상 POST 406 사례 있음. [HOSTING.md](HOSTING.md) §11의 `probe_waf.php`로 테스트 |
| 5 | PHP 확장 | `mysqli`(필수), `json`(필수), `iconv` 또는 `mbstring`(필수), `curl`·`openssl`·`gd`·`fileinfo`(권장) | `install/library.check.php` 실제 체크 항목 |
| 6 | `max_execution_time` | 30초 이상 | LLM 1건 3~8초, curl 타임아웃 25초 |
| 7 | `memory_limit` | 128MB 이상 | `problems.php` 320KB 배열 + 그누보드 |
| 8 | **무료 SSL + 자체 도메인** | 필수 | 유료 서비스에 HTTPS 없이는 결제·로그인 불가 |
| 9 | **상업적 용도 허용** | 약관 명시 확인 | 현재 무료 플랜이 상업 이용 금지라 애초에 이전 사유 |
| 10 | `.htaccess` `AllowOverride` | 필수 | `sql/`·`data/` 차단, gzip, 캐시 헤더. ⚠ nginx면 서버 설정으로 대체 |
| 11 | `data/` 쓰기 권한 | 필수 | 설치기가 `dbconfig.php`를 생성. 커뮤니티 관행 707 |
| 12 | `mail()` 또는 SMTP | 필수 | 회원가입 인증·비번찾기. 안 되면 Gmail SMTP 우회(그누보드5 지원) |

### 있으면 좋음

| 항목 | 없을 때 |
|---|---|
| **cron** | **불필요.** 만료·지급·알림을 전부 조회 시점 처리로 설계했다 |
| 외부 MySQL 접속 | phpMyAdmin 수동 export로 백업 |
| 웹루트 상위 파일 배치 | `.htaccess deny` + `<?php exit;` 가드 |
| SSH | FTP로 충분 |
| phpMyAdmin | 없으면 자체 install 스크립트 필요 |
| opcache | 없어도 320KB 파싱은 수십 ms |

**용량**: 그누보드5 약 50MB + 우리 앱 3MB + DB 수십MB = **최소 플랜으로 충분.** 요금이 아니라 위 1~4번 스펙으로 골라야 한다.

### 신청 전 검증 — 5분

`probe.php` + `probe_waf.php` 전문과 "보아야 할 것 우선순위"는 [HOSTING.md](HOSTING.md) §11에 있다. 핵심만:

1. **아웃바운드 curl 3개(DeepSeek / 토스 / 구글)가 전부 OK인가** — 하나라도 FAIL이면 그 업체 탈락
2. `curl`·`openssl`·`mysqli` 확장
3. **DB `SELECT VERSION()` 실제 숫자** — "MariaDB 10.x"의 정체를 밝히는 유일한 방법
4. `max_execution_time` ≥ 30 또는 `ini_set` 변경 가능
5. `@@collation_database` — 우리 `ex_*` 테이블을 여기 맞춘다
6. `InnoDB: YES`
7. `@@sql_mode`에 `NO_ZERO_DATE`가 있으면 그누보드 설치 SQL(`'0000-00-00 00:00:00'`)이 실패할 수 있다
8. **`1=1`·`UNION ALL`이 든 POST가 WAF를 통과하는가** — 지문 SQL 때문에 실제 리스크

### 계약 전 서면으로 물을 것

전 업체가 **PHP 확장 목록·리소스 한도·상업적 이용 약관을 공식 문서에 안 적는다.** [HOSTING.md](HOSTING.md) §10의 5개 질문을 문의한다.

---

## 10. 실행 순서 (다운타임 0)

기존 `/sqld/`를 살려둔 채 `/exam/`을 새로 만들고 검증이 끝나면 리다이렉트만 건다.

### Phase 0 — 준비 (1~2일, 대기 위주)

1. **자체 도메인 등록.** `*.ivyro.net`은 호스팅사 소유라 이전 시 링크·SEO가 전멸한다. OIDC/PG 콜백 URL도 도메인에 묶이므로 먼저 확정해야 두 번 일하지 않는다.
2. §9 체크리스트 + `probe.php`로 호스팅 선정 → 신청 → 네임서버 → SSL 확인.
3. **유튜브 30개 업로드(공개).** 원본 `06\videos\m01-1.static.mp4` … `m06-5.static.mp4`. 제목·설명·태그는 이미 있는 `app/routes_pipeline.py:319`의 `youtube_meta` 라우트로 생성. 회차별 재생목록 6개. `--init-youtube-map`으로 골격 만들고 URL의 `v=` 값 30개 복붙(20분).
4. **사업자등록 진행.** 계좌이체 수동 승인으로 받아도 사업자등록 의무는 발생한다([PAYMENT.md](PAYMENT.md) §6-②). 약관·환불규정·개인정보처리방침 준비 — 그누보드 템플릿을 시작점으로 쓰되 **환불규정(디지털 콘텐츠 청약철회 제한, 미사용분 환불 기준, 매월 소멸 고지)은 직접 써야 한다.** 특히 **"미사용 질문은 매월 소멸됩니다"는 구매 화면에서 별도 체크박스 동의**를 받는다.

### Phase 1 — 회원제 + 문제 DB + 질문 접수 (실작업 5~6일)

**문제 DB화로 1~2일 늘었다.** 정직하게 반영한다.

1. 그누보드5 최신(v5.6.34) 설치 (FTP → `/install/` → **`/install/` 삭제**)
2. 기본설정·SMTP → **소셜로그인 구글 키 발급·설정**(반나절) → 테마 색만 교체
3. `schema.sql` + `master.sql` (15테이블)
4. **`build_check.py` subject 픽스 + `exam_meta.py`** ← 서버 작업과 무관하게 먼저 해도 됨
5. `map_videos()` → `--emit-json`
6. **`adm/exam_import.php` + `exam_lib/problem.php`** ← 여기서 300문제를 DB에 넣는다
7. **`api/_boot.php` + `api/problems.php` + `api/grade.php`** (0.5일 추가)
8. `check_template.html` **5곳 개조** — `StaticDS`/`ApiDS` 추상화가 새로 추가된 부분 (0.5~1일 추가)
9. **`lib/credit.php` + `me/qna/credit.php`** (1.5일, 난이도 정점)
10. `buy.php`·`mypage.php`·`wrong.php`(오답노트)
11. `adm/admin.menu600.exam.php` + `exam_problem_list.php`·`exam_problem_form.php` + `exam_orders.php`·`exam_credit_grant.php`
12. `extend/10_exam.php` → `.htaccess` 3개
13. **`/exam/`에서 §11 검증** (기존 `/sqld/`는 살아 있음 = 다운타임 0)

**Phase 1 완료 시점: 문제풀이·서버채점·오답노트·질문접수가 되고, 답변은 관리자가 직접 쓴다.** 이 상태로도 서비스가 성립한다 — 질문 수가 적을 때는 오히려 이게 낫다.

**순서상 중요한 것**: 4번(subject 픽스)을 6번(임포트)보다 먼저 해야 한다. 안 그러면 `sj_name`이 300개 전부 "SQLD"로 DB에 들어가고 재임포트를 해야 한다.

### Phase 2 — LLM 초안 (실작업 2일)

DeepSeek 키 발급·배치 → `adm/exam_lib/llm.php`(provider 2분기 + 원가 계산 + `cost_cap`) → `adm/exam_lib/prompt.php`(캐싱 순서 준수) → `adm/exam_qna_list.php` 검수 화면 + 직렬 루프 + **키보드 단축키** → `adm/exam_qna_draft.php`·`exam_qna_form.php`(승인/반려/환불/쪽지) → **문제 카드 공개 Q&A 표시 + "해결됐어요" 버튼** → `adm/exam_index.php` 대시보드.

**모델 A/B**: 자격증별 실제 문제 20~30건으로 T1 후보 3개(DeepSeek V4-Flash / MiMo-V2.5 / Gemini 2.5 Flash-Lite) 비교. 결과를 `docs/model-eval.md`에 기록. 절차는 [COST.md](COST.md) §12.

**운영 흐름**: 하루 1~2회 검수 화면 접속 → [대기 초안 생성] → 진행률 보면서 대기 → 하나씩 읽고 승인. 12건 초안 1분, 검수 15분(단축키 적용 후).

### Phase 3 — 결제

**프로토타입 데모는 지금 가능하다** — 토스 공개 테스트 키로 빌링 전 플로우가 동작한다([PAYMENT.md](PAYMENT.md) §1). `od_method='pg_test'`로 기록하고 화면에 "테스트 결제" 배지를 고정한다.

**실운영 초기(구독자 30명 이하)는 계좌이체 수동 승인.** PG 가입비 220,000 + 연관리비 110,000 = 330,000원의 손익분기가 379건(구독자 32명 × 12개월)이므로 그 전에 PG를 도입하면 회수하지 못한다.

**실결제 전환(구독자 30명 초과)**: 사업자등록 완료 → PG 신청 → 접수 3영업일 + 카드사 심사 2주 + **정기결제 별도 심사**. 테스트 키를 라이브 키로 바꾸고 `od_method`를 `pg_test` → `pg`로 바꾸는 것이 코드 변경의 전부다.

`api/pay_ready.php` + `api/pay_webhook.php` 2파일. **`ex_order` 스키마 변경 0.**

**5.7의 `subscription/settle_tosspayments.inc.php`를 참고 구현으로 읽는다. 파일만 읽고 5.7로 업그레이드하지 않는다** — master 대비 25커밋(보안 패치 포함) 뒤처진 diverged 브랜치다.

다품목: `ex_product` 1행 + `build_check.py --pd adsp` → `/exam/?pd=adsp`. 질문권 공용이라 **PHP 코드 변경 0.**

### Phase 4 — 실기·논술 (별개 프로젝트급)

**정보처리기사 실기, 컴활 실기**는 문제 형태가 객관식이 아니어서 **문제 데이터 제작 파이프라인부터 다시** 만들어야 한다. 모델 티어 문제가 아니라 콘텐츠 문제다.

**논술·약술 채점**은 `ex_qna.kind='grade'`로 붙이되 **루브릭 작성이 선행 조건**이다. 루브릭 없이는 어느 모델을 써도 채점 일관성이 안 나오고, 그러면 관리자 검수가 사실상 재채점이 되어 건당 5분이 든다. 건당 40원 원가에 검수 5분이면 상품이 성립하지 않는다.

이 단계에 들어가기 전에 Phase 1~3이 실제 구독자로 검증되어 있어야 한다.

### 전환 (Phase 1 완료 후)

`/sqld/`에 `Redirect 301 /sqld/ /exam/` → 유튜브 매핑 검증 후 **`/sqld/videos/` 삭제(411MB 회수)** → 구 폴더를 `/sqld-old/`로 rename + deny(2주 롤백 경로) → 2주 후 완전 삭제.

### 작업량

| Phase | 실작업 | 누적 |
|---|---|---|
| 0 준비 | 1~2일 (대기 위주) | 2일 |
| 1 회원제 + **문제 DB** + 질문 접수 | **5~6일** | 8일 |
| 2 LLM 초안 | **2일** | 10일 |
| 3 결제 (테스트 → 실결제) | 2일 + 심사 대기 | — |
| 4 실기·논술 | 별개 프로젝트 | — |

문제 DB화로 Phase 1이 3~4일 → 5~6일이 됐다. 늘어난 것은 임포트 화면·`api/problems.php`·`api/grade.php`·`StaticDS`/`ApiDS` 추상화·문제 편집 화면이고, 대신 **오답노트·정답률 집계·문제 편집·검색이 함께 들어온다.** 나중에 붙이면 더 비싸므로 지금 하는 게 맞다.

AI 코딩 도구로 코드를 받아 검수·수정하는 방식 기준이다. 직접 타이핑하면 3배로 본다. 20년 만의 PHP 감각 회복에 초반 1일이 별도로 필요하다.

**월 고정비**: 호스팅 1,500~5,000원 + 도메인 약 1,400원 + LLM 300원 = **약 3,000~6,500원.** 상세는 [COST.md](COST.md) §3.

---

## 11. 검증

### A. 데이터 정합성 (로컬, 빌드 직후)

1. `06/check.html` 더블클릭(`file://`) → 계정칸·질문버튼이 **안 보인다** → 정적 폴백 정상
2. 과목 드롭다운에 **2개 항목**(`데이터 모델링의 이해`, `SQL 기본 및 활용`) → subject 버그 해소
3. 각 회차 50문제, 총 300문제, 6회차 전부
4. `06/videos/` 폴더가 **생성되지 않았다**
5. `problems.json`의 `problems` 배열 길이 = **300**, `subjects` = 2행, `rounds` = 6행
6. 채점 → 정답·해설 표시 정상 (**`StaticDS` 경로**로 클라이언트 채점)

### A2. 문제 임포트

7. `adm/exam_import.php`에 `problems.json` 업로드 → **신규 300 / 갱신 0 / 건너뜀 0 / 실패 0**
8. `SELECT COUNT(*) FROM ex_problem` → **300**. `ex_round.rd_count`가 6행 모두 50
9. **재임포트(같은 파일)** → **신규 0 / 갱신 0** (`pr_hash` 동일). `pr_id` 값이 **변하지 않는다** (`SELECT pr_id, pr_key` 스냅샷 비교)
10. 해설 1건을 `adm/exam_problem_form.php`에서 수정 → `edited_by`/`edited_at` 채워짐 → **재임포트 시 "건너뜀 1건"** 으로 보고되고 수정본이 살아 있다
11. "원본 복원" 클릭 → `edited_by` 비워짐 → 재임포트 시 원본으로 되돌아감
12. `ex_problem`에서 `sj_name`이 **2종**만 나온다 (`SELECT DISTINCT sj_name`)

### A3. 서버 채점·오답노트 (문제 DB화로 새로 생긴 검증)

13. `GET api/problems.php?pd=sqld&round=1` → 50문제. **`pr_open=0`으로 바꾼 문제 1건이 응답에서 빠진다**
14. 같은 요청 재호출 + `If-None-Match` → **304**. 문제를 1건 수정한 뒤 → **200**(ETag 무효화)
15. `POST api/grade.php` (로그인) → `score` 정확, `ex_attempt` 1행 + `ex_attempt_item` 50행, `ex_wrong` upsert
16. 같은 회차 재채점 → `ex_wrong.try_cnt` 증가, 행 수는 **늘지 않는다**(upsert)
17. **비로그인 채점** → `score`는 오지만 `ex_attempt`에 행이 **생기지 않는다**
18. **답안 화이트리스트**: 다른 회차의 `pr_key`를 섞어 POST → 그 키는 무시되고 정답이 새지 않는다. 형식이 깨진 키(`'; DROP`) → 정규식에서 거부

### B. 인증·질문권 (서버)

19. 그누보드 회원가입 → 인증 메일 도착. 구글 소셜로그인 → 신규 회원 자동 생성 → 헤더에 닉네임
20. `api/me.php` → `login:1`, `csrf` 존재, `count = floor(bal/unit)` 정확
21. `adm/exam_credit_grant.php`에서 30원 지급 → 헤더가 **`질문 3개`** (단가 미표시 확인)
22. **초과 차감 테스트**: 잔액 10원으로 만들고 탭 2개에서 동시 전송 → 하나만 성공, 하나는 `402`. `lot_used`가 `lot_qty`를 **넘지 않는다**
23. **여러 lot 걸침 테스트**: 7원 lot + 7원 lot 상태에서 10원 차감 → 첫 lot 7 + 둘째 lot 3 소모, 잔액 4원
24. **부분 실패 되돌림 테스트**: 루프 중간 실패를 강제 주입 → 차감된 만큼 환불되고 잔액이 원복되는지
25. **이중 지급 테스트**: 탭 2개에서 `api/me.php` 동시 호출(월 경계 상황) → `ex_credit_lot`에 같은 `lot_period` 행이 **1개만** (UNIQUE 제약)
26. **소멸 테스트**: `lot_expire`를 어제로 UPDATE → 잔액 즉시 0. `ex_credit_ledger`에 `expire` 행이 lazy 생성되고 **재조회 시 중복 생성되지 않는다**
27. **월 drip 테스트**: `next_grant_on`을 두 달 전으로 UPDATE → `api/me.php` 1회 호출로 2개월분 lot 생성, 첫 달은 만료 상태
28. 정합성 쿼리(§5-6) → `ledger_sum`과 `lot_avail` 일치
29. CSRF 없이 `POST api/qna.php` → **403**. 비로그인 → **401**
30. **`$member['mb_level']`만 보는 코드가 없는지** grep (비로그인도 1이다)

### C. 노출 방지

31. `api/qna.php?mine=1` 응답에 **`qa_draft` 문자열이 없다** (grep)
32. `/exam/sql/schema.sql` 직접 접근 → **403**
33. 업로드한 `problems.json`이 웹루트에 남아 있지 않다 (임포트 후 삭제 또는 `deny`)
34. API 키 파일 직접 접근 → **403** 또는 빈 출력
35. 일반 회원 계정으로 `/adm/exam_qna_list.php`·`exam_import.php`·`exam_problem_form.php` → **전부 거부** (`auth_check_menu`)
36. **JSON 엔드포인트 응답에 HTML/`alert(` 이 섞이지 않는다** (`check_token()` 미사용 확인)
37. `adm/exam_problem_form.php` 저장 시 XSS — 해설에 `<script>`를 넣어보고 화면에서 이스케이프되는지

### D. LLM (Phase 2)

38. `adm/exam_qna_draft.php` 1건 → 8초 내 응답, `draft_ready`
39. 같은 문제로 2번째 질문 → `qa_tok_cache > 0` → **프롬프트 캐싱 작동 확인**
40. `qa_cost`가 `ex_product.cost_cap` 미만
41. 초안이 빈 상태로 [승인] → **422 거부**
42. [반려] → `refund` 원장 행(`lg_amt = +ex_qna.cost_units`), 잔액 복구, `qa_refunded=1`
43. `[검수필요]`로 시작하는 초안이 노란 배경으로 강조
44. **같은 문제에 승인된 공개 답변이 있으면 질문 폼 위에 먼저 표시되고, "해결됐어요"를 누르면 질문권이 차감되지 않는다**
45. 키보드 단축키(Enter/J/R) 동작
46. **문제 오류 신고** → 관리자 화면에 뜨고 `pr_open=0` 처리 시 `api/problems.php`에서 즉시 사라진다. 신고에 질문권이 차감되지 않는다

### E. 결제 (Phase 3)

47. 토스 테스트 키로 빌링키 발급 → `ex_billing` 1행, `is_test=1`
48. 1,100원 테스트 승인 → `ex_order` `od_method='pg_test'`, `od_status='paid'`, `od_pg_tid` 채워짐
49. 승인 후 `ex_entitlement` 생성 + 첫 달 lot 지급
50. 화면에 **"테스트 결제" 배지**가 보인다
51. `ex_billing`이 관리자 화면에서 `card_last4`만 노출 (`billing_key` 미노출)

### F. 전환 후

52. `https://도메인/sqld/check.html` → `/exam/`으로 301
53. 서버에 `.mp4` 파일 0개
54. 유튜브 30개 embed 전부 재생

### G. 호스팅 (계약 전, [HOSTING.md](HOSTING.md) §11)

55. `probe.php` — 아웃바운드 curl 3개 OK, `curl`/`openssl`/`mysqli` 확장, `SELECT VERSION()` 실제 숫자, `max_execution_time` ≥ 30, `InnoDB: YES`, `@@collation_database`
56. **`probe_waf.php` — `1=1`·`UNION ALL`이 든 POST가 통과한다.** 406/403이면 그 업체에서는 질문 등록이 막힌다
57. 확인 후 `probe*.php` **삭제**

---

## 12. 리스크와 미결

### 감수해야 하는 것

1. **문제·정답·해설은 완전 공개다.** 복사·재배포를 막을 수 없다. 이 수익 모델의 전제이므로 문제는 아니지만, **콘텐츠가 차별점이 아니고 Q&A 대응 품질이 유일한 차별점**이라는 뜻이다. 자원을 거기에 집중해야 한다.
2. **검수 노동이 100명 근처에서 무너진다.** 인건비로 환산하면 어떤 규모에서도 적자다([COST.md](COST.md) §3). 검수 효율화가 유일하게 의미 있는 원가 절감이고, B2B 도입 시 계약 전에 검수 주체를 결정해야 한다.
3. **LLM 답변 품질 리스크.** 저가 모델은 계산과 다단 추론에서 **조용히** 틀린다. 규칙 2의 자진 신고 + 관리자 검수가 유일한 방어선이고, 검수를 건너뛰는 순간 신뢰가 무너진다. **자동 승인을 만들지 않는 것이 설계 결정이다.**
4. **outbound curl이 막힌 호스팅을 고르면 Phase 2가 통째로 불가능해진다.** §9의 4번을 신청 전에 서면 확인해야 한다. 폴백(로컬 도구에서 pull→생성→push)은 존재하지만 검수하려면 PC를 켜야 해서 열등하다.
5. **그누보드5는 8주에 8개 릴리스가 나오는 스택이다.** 보안 패치가 다수 포함된다. GitHub 릴리스 알림을 켜고, 코어를 절대 포크하지 않고, 사이트 전체를 git으로 버전관리한다([GNUBOARD-FACTS.md](GNUBOARD-FACTS.md) §11~§12).
6. **`_index.json`의 `reviewed`가 300개 전부 false**, `verified`는 `.md`에만 있다. 검수 상태를 실제로 활용하려면 `02/` 생성 파이프라인부터 정리해야 한다(범위 밖).

### 미결 — 확인 필요

**호스팅** ([HOSTING.md](HOSTING.md) §12에 전체 목록)
- 카페24/닷홈의 **MariaDB·MySQL 정확한 마이너 버전** — "10.x"/"8.x"로만 표기돼 있다
- 전 업체 **PHP 확장 목록·`max_execution_time`·상업적 이용 약관** — 공식 문서에 존재하지 않음
- **WAF가 SQL 문자열 POST를 차단하는지** — 지문에 SQL이 들어가므로 실제 리스크
- 후이즈·웹티즌 사양 (SSO 리다이렉트 / 403으로 조회 불가)

**그누보드 세부** ([GNUBOARD-FACTS.md](GNUBOARD-FACTS.md) §14에 전체 목록)
- `sql_affected_rows()` 정확한 함수명 — §5 차감 코드의 전제
- 신규 설치본 **기본 콜레이션** — `ex_*`를 여기 맞춰야 `g5_member` 조인 시 충돌 없음
- `G5_TOKEN_ENCRYPTION_KEY` 정의 위치 — 반드시 랜덤값으로 설정해야 함
- 공식 업데이트 절차(덮어쓰기 vs 전체 교체) — §11 안전성의 전제
- `G5_IS_MOBILE` 분기 우회 방법

**결제** ([PAYMENT.md](PAYMENT.md) §8에 전체 목록)
- 정기결제 카드결제에 **건당 고정액이 붙는지** (계약서에는 컬럼 없음 — 계약 시 서면 확인)
- **영세 우대요율(1.50%)이 정기결제 행에도 적용되는지**
- 이행보증보험 실제 요구 금액
- 통신판매업 신고 시 에스크로 확인증 실제 면제 여부 (관할 구청)

**실측 (Phase 2 가동 후 한 달)**
- 캐시 히트율 / 1인당 월 질문 수 / 검수 1건 소요 시간 / 자격증별 모델 A/B 결과

---

## 13. 핵심 파일

- `scripts/build_check.py` — `:96` subject 폴백 버그 픽스, `:119` `copy_videos()` → `map_videos()`(mp4 복사 폐기), **`--emit-json`**(임포트용) 추가. 파이프라인 유일 진입점
- `scripts/check_template.html` — 개조 **5곳**: **`StaticDS`/`ApiDS` 데이터소스 추상화(신규)**, 채점을 서버로(`:293-304`), 유튜브 iframe(`:154`/`:320`/`:344`/`:347`), 헤더 `#acct`, `:262-275`에 `[질문하기]`+공개 Q&A+오류신고. **마크다운 렌더러(`:172-211`)·이론 Shadow DOM(`:330`)은 무수정** — 가장 값진 자산
- `web/exam/api/lib/credit.php` (신규) — 조건부 UPDATE 기반 차감·환불·잔액·월 drip·lazy 만료. **정확성이 가장 중요한 파일.** 부분 실패 되돌림 경로를 반드시 테스트
- `web/adm/exam_import.php` + `exam_lib/problem.php` (신규) — `problems.json` upsert. **`edited_by`가 있으면 건너뛰는 규칙**이 핵심. `pr_id`를 절대 바꾸지 않는다(DELETE+INSERT 금지)
- `web/exam/api/problems.php` + `grade.php` (신규) — DB에서 문제 서빙 + 서버 채점. `pr_open=0` 필터, ETag, 답안 화이트리스트 검증
- `web/adm/exam_qna_list.php` + `exam_qna_draft.php` + `exam_lib/llm.php` (신규) — 서버 curl LLM 호출을 JS 직렬 루프로 1건씩 처리해 `max_execution_time`을 회피하는 핵심 구조
- `web/sql/schema.sql` (신규) — **15테이블.** `g5_member` 미변경 + `ex_user_ext` 분리, **`ex_problem`(정답·해설 포함, `edited_by` 보호, FULLTEXT)**, `ex_entitlement`(drip) + `ex_credit_lot`(원 단위) + `ex_credit_ledger`(감사), `ex_attempt*`/`ex_wrong`(오답노트·정답률), **InnoDB + utf8mb4 필수**, `UNIQUE(mb_id, lot_src, lot_period)`로 이중 지급 차단
- `web/adm/admin.menu600.exam.php` (신규) — 파일 추가만으로 관리자 메뉴 등록. 코어 수정 0
- `D:\00work\ocr-output-260723\02\_index.json` + `02\m01-01.md` — 과목/verified/needs_review의 유일한 출처. `src_id = f"m{round:02d}-{number:02d}"`로 lesson 블록과 **300/300 무손실 조인 확인 완료.** ⚠ 웹에서 수정한 것은 **주기적으로 여기로 역반영**해야 한다 — 안 하면 재임포트가 수정을 되돌린다
