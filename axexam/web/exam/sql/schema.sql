-- ============================================================================
--  ex_* 스키마 — 문제은행 + 질문권 Q&A                              15 테이블
--  대상: 카페24 axexam · MariaDB 10.6.17 · DB 콜레이션 utf8mb3_general_ci
--  실행: 카페24 콘솔 → phpMyAdmin → SQL 탭에 붙여넣기 (1회)
-- ============================================================================
--
--  ■ 테이블명은 `ex_` 무접두다. G5_TABLE_PREFIX(g5_)를 붙이지 않는다.
--    우리 테이블은 그누보드 테이블이 아니므로 네임스페이스를 섞지 않는다.
--    extend/10_exam.php 에도 리터럴 'ex_qna' 로 등록한다.
--
--  ■ 엔진은 전부 InnoDB 다. 그누보드 코어(g5_*)는 MyISAM 이라 트랜잭션이 없지만,
--    크레딧 차감의 조건부 UPDATE 는 행 잠금이 필요하다.
--    (트랜잭션을 쓰는 게 아니라 `UPDATE ... WHERE lot_used + n <= lot_qty` +
--     affected_rows 판별 패턴이다. 그누보드 insert_use_point() 가 검증한 방식.)
--
--  ■ ★★ 콜레이션 혼용 — 이 스키마에서 가장 틀리기 쉬운 지점 ★★
--    실측: 이 DB 의 기본 콜레이션이 utf8mb3_general_ci 다(= 옛 "utf8", 3바이트).
--    그래서 g5_member.mb_id 도 utf8mb3 다.
--
--      · 테이블 기본은 utf8mb4  → 질문 본문에 이모지가 들어간다
--      · mb_id 계열 컬럼만 utf8mb3 → g5_member 와 JOIN 할 때 충돌하지 않는다
--
--    utf8mb3 지정을 빠뜨리면 다음이 런타임에 터진다:
--      ERROR 1267: Illegal mix of collations
--        (utf8mb4_general_ci,IMPLICIT) and (utf8mb3_general_ci,IMPLICIT)
--    적용 대상: mb_id, lg_by(관리자), edited_by(관리자)
--
--    ⚠ `utf8mb3` 키워드는 MariaDB 10.6+ 에서 유효하다. 구버전에서 문법 오류가 나면
--       utf8mb3 → utf8, utf8mb3_general_ci → utf8_general_ci 로 일괄 치환한다.
--
--  ■ FULLTEXT 인덱스는 만들지 않는다.
--    MySQL 8.0 의 ngram 파서가 MariaDB 에는 없다. MariaDB 기본 토크나이저는
--    공백 기준이라 조사가 붙는 한국어("슈퍼타입을" vs "슈퍼타입의")에서 무용지물이다.
--    관리자 문제 검색은 LIKE 로 한다 — 자격증 5종 × 300 = 1,500행이라 풀스캔이 수 ms 다.
-- ============================================================================

SET NAMES utf8mb4;


-- ── 1. 품목 (자격증군) ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ex_product (
  pd_id      VARCHAR(20)  NOT NULL PRIMARY KEY,      -- 'sqld','adsp','gisa-w','gisa-p','comp'
  pd_name    VARCHAR(100) NOT NULL,
  pd_open    TINYINT      NOT NULL DEFAULT 1,
  tier       VARCHAR(4)   NOT NULL DEFAULT 'T1',
  model_id   VARCHAR(48)  NOT NULL DEFAULT 'deepseek-v4-flash',
  provider   VARCHAR(16)  NOT NULL DEFAULT 'openai_compat',  -- openai_compat | anthropic
  cost_units SMALLINT     NOT NULL DEFAULT 10,       -- 질문 1건당 차감(원)
  cost_cap   DECIMAL(8,4) NOT NULL DEFAULT 3.0000,   -- 건당 원가 경고 상한(원)
  pd_config  TEXT         NULL,                      -- JSON: 무료 공개 범위 등 미확정 정책값
  pd_sort    INT          NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ── 2. 판매 상품 ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ex_plan (
  pl_id     INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  pl_name   VARCHAR(60)  NOT NULL,       -- '월 100개 · 1개월'
  pl_price  INT          NOT NULL,       -- 1100 (VAT 포함)
  pl_months SMALLINT     NOT NULL,       -- 1 / 3 / 12
  pl_quota  INT          NOT NULL,       -- 월 지급액(원). 1000 = 질문 100개
  pl_open   TINYINT      NOT NULL DEFAULT 1,
  pl_sort   INT          NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ── 3. 회차 ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ex_round (
  pd_id    VARCHAR(20)  NOT NULL,
  rd_no    SMALLINT     NOT NULL,
  rd_label VARCHAR(100) NOT NULL,        -- '자사 모의고사 01회'
  rd_free  TINYINT      NOT NULL DEFAULT 1,   -- 무료 공개 스위치 (현재 전부 1)
  rd_open  TINYINT      NOT NULL DEFAULT 1,
  rd_count SMALLINT     NOT NULL DEFAULT 0,   -- 문제 수 (임포트가 채운다)
  PRIMARY KEY (pd_id, rd_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ── 4. ★ 문제 — 정답·해설 포함 (공개니까 한 테이블) ────────────────────────
--
--  ⚠⚠ pr_id 는 절대 바뀌면 안 된다. ex_attempt_item / ex_wrong 이 FK 로 참조한다.
--      upsert 축은 UNIQUE (pd_id, pr_key) 이고 **DELETE + INSERT 는 금지**다.
--      재임포트로 pr_id 가 갈리면 회원의 오답노트와 정답률 집계가 통째로 끊긴다.
--
--  ⚠  edited_by 가 비어 있지 않으면 임포트가 그 행을 건너뛴다(웹 수정본 보호).
--      대신 그 수정은 주기적으로 02/ 원본으로 역반영해야 한다 —
--      안 하면 언젠가 02/ 가 낡아서 "원본 복원" 시 수정이 되돌아간다.
--
CREATE TABLE IF NOT EXISTS ex_problem (
  pr_id        INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  pd_id        VARCHAR(20)  NOT NULL,
  rd_no        SMALLINT     NOT NULL,
  pr_key       VARCHAR(40)  NOT NULL,   -- 'm01-1#7' = check.html 의 keyOf(). 클라이언트 식별자
  bundle       VARCHAR(20)  NOT NULL,   -- 'm01-1'
  pr_no        SMALLINT     NOT NULL,   -- 1..50
  src_id       VARCHAR(20)  NOT NULL,   -- 'm01-07' (02/ 원본 id)
  src_from     VARCHAR(20)  NOT NULL DEFAULT '',   -- derived_from '01-07'
  sj_no        TINYINT      NOT NULL DEFAULT 0,
  sj_name      VARCHAR(100) NOT NULL DEFAULT '',   -- 비정규화 (조인 절약)
  difficulty   VARCHAR(4)   NOT NULL DEFAULT '',   -- 상/중/하
  question     MEDIUMTEXT   NOT NULL,
  passage      MEDIUMTEXT   NULL,
  sql_text     MEDIUMTEXT   NULL,
  table_json   TEXT         NULL,       -- {columns:[],rows:[[]]}
  figures_json TEXT         NULL,       -- ["m01-01-super.svg"]
  choices_json TEXT         NOT NULL,   -- ["①문구",...] 순서가 answer_index 기준
  n_choices    TINYINT      NOT NULL DEFAULT 4,
  answer_index TINYINT      NULL,       -- 0-based
  answer_label VARCHAR(8)   NOT NULL DEFAULT '',   -- '②'
  explanation  MEDIUMTEXT   NULL,
  tags_json    TEXT         NULL,
  has_figure   TINYINT      NOT NULL DEFAULT 0,
  has_sql      TINYINT      NOT NULL DEFAULT 0,
  has_table    TINYINT      NOT NULL DEFAULT 0,
  verified     TINYINT      NOT NULL DEFAULT 0,   -- 02/*.md frontmatter 에서 복원
  reviewed     TINYINT      NOT NULL DEFAULT 0,
  needs_review TINYINT      NOT NULL DEFAULT 0,
  pr_open      TINYINT      NOT NULL DEFAULT 1,   -- 0 = 숨김 (오류 신고 시 즉시 차단)
  pr_hash      CHAR(32)     NOT NULL DEFAULT '',  -- 콘텐츠 md5 → 변경분만 UPDATE
  -- ★ 웹에서 수정한 관리자. 비어 있지 않으면 재임포트에서 제외한다
  edited_by    VARCHAR(20)  CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci NOT NULL DEFAULT '',
  edited_at    DATETIME     NULL,
  updated_at   DATETIME     NOT NULL,   -- ETag 계산에 쓴다. 임포트/편집이 명시적으로 세팅
  UNIQUE KEY uq_key    (pd_id, pr_key),
  KEY        idx_round (pd_id, rd_no, pr_no),
  KEY        idx_rev   (pd_id, needs_review, pr_open),
  KEY        idx_src   (src_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ── 5. 회원 확장 (g5_member 는 절대 변경하지 않는다) ────────────────────────
CREATE TABLE IF NOT EXISTS ex_user_ext (
  mb_id      VARCHAR(20) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci NOT NULL PRIMARY KEY,
  qna_total  INT         NOT NULL DEFAULT 0,
  agree_at   DATETIME    NULL,          -- 유료 약관·"매월 소멸" 조항 동의 시각
  blocked    TINYINT     NOT NULL DEFAULT 0,
  memo       VARCHAR(255) NOT NULL DEFAULT '',
  created_at DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ── 6. 구독권 = 월 지급의 원천 (drip source) ────────────────────────────────
CREATE TABLE IF NOT EXISTS ex_entitlement (
  mb_id          VARCHAR(20) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci NOT NULL,
  pd_id          VARCHAR(20)  NOT NULL DEFAULT '',   -- '' = 전 품목 공용
  monthly_quota  INT          NOT NULL,              -- 월 지급액(원)
  months_paid    SMALLINT     NOT NULL,
  months_granted SMALLINT     NOT NULL DEFAULT 0,
  next_grant_on  DATE         NOT NULL,
  started_on     DATE         NOT NULL,
  od_id          INT UNSIGNED NOT NULL DEFAULT 0,
  updated_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (mb_id, pd_id),
  KEY idx_grant (next_grant_on)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ── 7. 질문권 묶음 (지급 1건 = 1 lot). lot_qty / lot_used 단위는 '원' ───────
--
--  ★ UNIQUE KEY uq_month 가 이 설계에서 가장 중요한 제약이다.
--    회원이 탭 두 개에서 동시에 api/me.php 를 호출해도(월 경계 상황)
--    같은 달 지급분이 두 번 들어가지 않는다. 애플리케이션 락이 필요 없다.
--
--  ★ 만료는 배치가 아니라 조회 시점 판정이다 —
--    잔액 쿼리가 `lot_expire >= CURDATE()` 로 거르므로 cron 이 필요 없다.
--    (카페24 공유호스팅은 cron 과 event_scheduler 를 공식 미지원한다.)
--
CREATE TABLE IF NOT EXISTS ex_credit_lot (
  lot_id         INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  mb_id          VARCHAR(20) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci NOT NULL,
  lot_src        VARCHAR(10) NOT NULL DEFAULT 'monthly',  -- monthly|topup|promo|manual|refund
  lot_period     CHAR(7)     NOT NULL DEFAULT '',         -- '2026-08' 어느 달 지급분
  lot_qty        INT         NOT NULL,                    -- 지급액(원)
  lot_used       INT         NOT NULL DEFAULT 0,          -- ★ 조건부 UPDATE 대상
  lot_expire     DATE        NOT NULL,                    -- 이 날짜까지 유효(포함)
  lot_exp_logged TINYINT     NOT NULL DEFAULT 0,          -- 만료 원장 기록 여부 (lazy)
  lot_note       VARCHAR(120) NOT NULL DEFAULT '',
  created_at     DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_month (mb_id, lot_src, lot_period),  -- ★ 이중 지급 DB 차원 차단
  KEY        idx_bal  (mb_id, lot_expire, lot_used)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ── 8. 원장 (append-only. UPDATE/DELETE 금지 — 정정도 새 행으로) ────────────
CREATE TABLE IF NOT EXISTS ex_credit_ledger (
  lg_id      BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  mb_id      VARCHAR(20) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci NOT NULL,
  lot_id     INT UNSIGNED NOT NULL DEFAULT 0,
  lg_type    VARCHAR(10)  NOT NULL,       -- grant|debit|refund|expire|adjust
  lg_amt     INT          NOT NULL,       -- + 지급/환불, - 차감/만료 (원 단위)
  lg_ref     VARCHAR(40)  NOT NULL DEFAULT '',  -- 'qna:1234' / 'order:88'  ← 멱등키
  lg_bal     INT          NOT NULL DEFAULT 0,   -- 기록 시점 잔액 스냅샷(감사용)
  lg_by      VARCHAR(20) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci NOT NULL DEFAULT '',
  lg_memo    VARCHAR(180) NOT NULL DEFAULT '',
  created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_mb  (mb_id, created_at),
  KEY idx_ref (lg_ref)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ── 9. 주문 (수동 승인 → PG. 스키마 변경 0) ─────────────────────────────────
--  내부 오픈 단계에서는 od_method='manual'/'free' 가 실운영 경로다.
CREATE TABLE IF NOT EXISTS ex_order (
  od_id        INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  mb_id        VARCHAR(20) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci NOT NULL,
  pl_id        INT UNSIGNED NOT NULL,
  od_price     INT          NOT NULL,
  od_months    SMALLINT     NOT NULL,
  od_quota     INT          NOT NULL,
  od_method    VARCHAR(12)  NOT NULL DEFAULT 'bank',    -- bank|pg_test|pg|free|coupon|manual
  od_depositor VARCHAR(40)  NOT NULL DEFAULT '',
  od_status    VARCHAR(12)  NOT NULL DEFAULT 'pending', -- pending|paid|canceled|refunded
  od_pg_tid    VARCHAR(64)  NOT NULL DEFAULT '',        -- 토스 paymentKey
  admin_memo   VARCHAR(255) NOT NULL DEFAULT '',
  created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  paid_at      DATETIME     NULL,
  KEY idx_mb (mb_id, created_at),
  KEY idx_st (od_status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ── 10. 빌링키 (Phase 3) ────────────────────────────────────────────────────
--  ⚠ billing_key 는 결제수단 그 자체다. 유출되면 임의 청구가 가능하다.
--    이 테이블 접근을 결제 코드로만 제한하고, 관리자 화면에도 card_last4 만 표시한다.
CREATE TABLE IF NOT EXISTS ex_billing (
  mb_id        VARCHAR(20) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci NOT NULL PRIMARY KEY,
  customer_key VARCHAR(64)  NOT NULL,   -- 토스 customerKey (특수문자 1개 이상 필수)
  billing_key  VARCHAR(255) NOT NULL,
  card_company VARCHAR(40)  NOT NULL DEFAULT '',
  card_last4   CHAR(4)      NOT NULL DEFAULT '',
  pg           VARCHAR(16)  NOT NULL DEFAULT 'toss',
  is_test      TINYINT      NOT NULL DEFAULT 1,
  created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_ck (customer_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ── 11. Q&A ─────────────────────────────────────────────────────────────────
--
--  ★★ qa_draft 와 qa_answer 를 다른 컬럼으로 둔 것이 이 시스템의 핵심 안전장치다.
--     회원용 API 는 qa_answer 만 SELECT 하고 qa_draft 는 SELECT 목록에 넣지 않는다.
--     → LLM 환각이 검수 없이 공개되는 경로가 구조적으로 존재하지 않는다.
--     자동 승인을 만들지 않는 것이 설계 결정이다.
--
--  ★ cost_units 를 질문 행에도 저장하는 이유: 차감 단가가 나중에 바뀌어도
--    과거 질문의 환불액이 정확하다.
--
CREATE TABLE IF NOT EXISTS ex_qna (
  qa_id       INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  qa_parent   INT UNSIGNED NOT NULL DEFAULT 0,   -- 재질문 스레드 (별도 차감)
  mb_id       VARCHAR(20) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci NOT NULL,
  pd_id       VARCHAR(20)  NOT NULL DEFAULT 'sqld',
  kind        VARCHAR(8)   NOT NULL DEFAULT 'qna',   -- qna | grade (논술 채점, Phase 4)
  pr_key      VARCHAR(40)  NOT NULL DEFAULT '',      -- 'm01-1#7'. 일반질문은 빈값
  qa_question MEDIUMTEXT   NOT NULL,                 -- utf8mb4 → 이모지 OK
  qa_chosen   TINYINT      NOT NULL DEFAULT -1,      -- 질문자가 고른 보기
  qa_status   VARCHAR(12)  NOT NULL DEFAULT 'pending',
      -- pending → drafting → draft_ready → approved | rejected
  qa_draft    MEDIUMTEXT   NULL,     -- ★ LLM 초안. 회원 API 에서 절대 SELECT 안 함
  qa_answer   MEDIUMTEXT   NULL,     -- 관리자 확정 = 공개되는 것
  qa_model    VARCHAR(48)  NOT NULL DEFAULT '',
  qa_tok_in    INT         NOT NULL DEFAULT 0,
  qa_tok_cache INT         NOT NULL DEFAULT 0,   -- 캐시 히트 토큰 (원가 추적)
  qa_tok_out   INT         NOT NULL DEFAULT 0,
  qa_cost      DECIMAL(8,4) NOT NULL DEFAULT 0,  -- 실측 원가(원)
  cost_units   SMALLINT    NOT NULL DEFAULT 10,  -- 실제 차감액(원)
  qa_credit_ok TINYINT     NOT NULL DEFAULT 0,   -- 0 이면 검수 화면에 빨간 경고
  qa_refunded  TINYINT     NOT NULL DEFAULT 0,   -- 중복 환불 방지
  qa_public    TINYINT     NOT NULL DEFAULT 1,
  qa_draft_at    DATETIME  NULL,
  qa_answered_at DATETIME  NULL,
  created_at     DATETIME  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_st  (qa_status, created_at),
  KEY idx_mb  (mb_id, created_at),
  KEY idx_pub (pr_key, qa_status, qa_public)   -- 문제별 공개 Q&A = FAQ 조회
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ── 12~13. 채점 이력 (문제를 DB 에 넣어서 되살아난 것) ──────────────────────
CREATE TABLE IF NOT EXISTS ex_attempt (
  at_id      INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  mb_id      VARCHAR(20) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci NOT NULL,
  pd_id      VARCHAR(20) NOT NULL,
  rd_no      SMALLINT    NOT NULL,
  at_total   SMALLINT    NOT NULL,
  at_correct SMALLINT    NOT NULL,
  at_pct     TINYINT     NOT NULL,
  at_sec     INT         NOT NULL DEFAULT 0,
  at_filter  VARCHAR(60) NOT NULL DEFAULT '',   -- 과목/난이도 필터 상태
  created_at DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_mb (mb_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ex_attempt_item (
  at_id  INT UNSIGNED NOT NULL,
  pr_id  INT UNSIGNED NOT NULL,
  chosen TINYINT      NOT NULL DEFAULT -1,   -- -1 = 미응답
  is_ok  TINYINT      NOT NULL DEFAULT 0,
  PRIMARY KEY (at_id, pr_id),
  KEY idx_pr (pr_id, is_ok)   -- ★ 전체 정답률 집계 = 문제 품질 지표
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ── 14. 오답노트 (문제별 최신 상태, upsert) ─────────────────────────────────
--  회원에게 무료로 준다. 유료 가치는 Q&A 에 있고 이건 재방문 유도 장치다.
CREATE TABLE IF NOT EXISTS ex_wrong (
  mb_id       VARCHAR(20) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci NOT NULL,
  pr_id       INT UNSIGNED NOT NULL,
  try_cnt     SMALLINT NOT NULL DEFAULT 0,
  wrong_cnt   SMALLINT NOT NULL DEFAULT 0,
  last_chosen TINYINT  NOT NULL DEFAULT -1,
  last_ok     TINYINT  NOT NULL DEFAULT 0,
  starred     TINYINT  NOT NULL DEFAULT 0,
  updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (mb_id, pr_id),
  KEY idx_mb (mb_id, last_ok, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ── 15. 로그 (rate limit + 남용 탐지) ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS ex_log (
  lo_id      BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  mb_id      VARCHAR(20) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci NOT NULL DEFAULT '',
  lo_act     VARCHAR(16) NOT NULL,        -- qna|draft|order|login|report
  lo_ref     VARCHAR(40) NOT NULL DEFAULT '',
  lo_ip      VARCHAR(45) NOT NULL DEFAULT '',   -- IPv6 대비 45
  created_at DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_mb (mb_id, lo_act, created_at),
  KEY idx_ip (lo_ip, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ============================================================================
--  실행 후 검증 — 아래를 그대로 돌려 결과를 확인한다
-- ============================================================================
--
-- (1) 15개가 InnoDB / utf8mb4 로 만들어졌는가
--
--   SELECT TABLE_NAME, ENGINE, TABLE_COLLATION
--     FROM information_schema.TABLES
--    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME LIKE 'ex\_%'
--    ORDER BY TABLE_NAME;
--   -- 15행 · ENGINE 전부 InnoDB · TABLE_COLLATION 전부 utf8mb4_general_ci(또는 _0900_ai_ci)
--
-- (2) ★ mb_id 계열이 g5_member.mb_id 와 같은 콜레이션인가 — 가장 중요
--
--   SELECT TABLE_NAME, COLUMN_NAME, COLLATION_NAME
--     FROM information_schema.COLUMNS
--    WHERE TABLE_SCHEMA = DATABASE()
--      AND (TABLE_NAME LIKE 'ex\_%' OR TABLE_NAME = 'g5_member')
--      AND COLUMN_NAME IN ('mb_id','lg_by','edited_by')
--    ORDER BY TABLE_NAME;
--   -- COLLATION_NAME 이 전부 동일해야 한다. 하나라도 utf8mb4_* 면 조인에서 1267 이 난다.
--
-- (3) 실제 조인이 되는가 (이게 통과해야 진짜 끝난 것)
--
--   SELECT COUNT(*) FROM ex_user_ext u JOIN g5_member m ON m.mb_id = u.mb_id;
--   -- 0 이라도 상관없다. **에러 없이 0 이 나오면 성공.**
--   -- ERROR 1267 Illegal mix of collations 가 나면 위 (2)를 다시 본다.
--
-- (4) 이중 지급 차단 제약이 살아 있는가
--
--   SHOW INDEX FROM ex_credit_lot WHERE Key_name = 'uq_month';
--   -- 3행 (mb_id, lot_src, lot_period) · Non_unique = 0
--
-- ============================================================================
