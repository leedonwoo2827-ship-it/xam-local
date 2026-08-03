-- ============================================================================
--  migrate-001-multipd.sql — 문제집별 수강·포인트 구조로 전환
--
--  왜 필요한가
--    스키마는 절반만 다품목이었다. ex_problem · ex_round · ex_entitlement ·
--    ex_attempt 는 pd_id 를 갖는데 **ex_order · ex_plan · ex_credit_lot ·
--    ex_credit_ledger 에는 없었다.** 그 상태로 문제집을 하나 더 열면:
--
--      · 주문이 pl_id 만 기록하니 "어느 문제집을 신청했는가"가 DB 에 남지 않는다
--      · buy.php 의 중복 검사가 품목을 안 보므로(mb_id + pending 만 확인)
--        SQLD 를 신청한 회원은 빅데이터를 **아예 신청할 수 없다**
--      · 포인트가 전 품목 공용 풀이라 SQLD 를 결제해 빅분기 질문에 쓸 수 있다
--      · ★ uq_month(mb_id, lot_src, lot_period) 때문에 두 문제집을 수강하는 회원의
--        같은 달 두 번째 월 지급이 **DB 차원에서 거부된다** — 가장 찾기 어려운 결함
--
--  안전성
--    · ADD COLUMN IF NOT EXISTS / ADD INDEX IF NOT EXISTS 라 여러 번 돌려도 안전하다
--      (MariaDB 10.0+ 문법. 이 서버는 10.6+ 다 — schema.sql §콜레이션 주석 참조)
--    · DROP TABLE · DELETE 없음. 기존 행은 pd_id = 'sqld' 로 backfill 한다 —
--      지금까지 존재한 품목이 SQLD 하나뿐이므로 이 값이 정확하다
--    · 기존 pl_id 1·2·3 은 값을 바꾸지 않는다. 바뀌면 ex_order.pl_id 참조가 끊긴다
--    · **컬럼 추가와 backfill 뿐이라 적용 후에도 기존 코드가 그대로 돈다.**
--      그래서 DB 를 먼저 올려도 사이트가 멈추지 않는다
--
--  ⚠ 인덱스 DROP → ADD 순서를 지킨다. 반대로 하면 같은 이름의 키가 이미 있어 실패한다.
-- ============================================================================

SET NAMES utf8mb4;


-- ── 1. ex_order 에 pd_id ────────────────────────────────────────────────────
ALTER TABLE ex_order
  ADD COLUMN IF NOT EXISTS pd_id VARCHAR(20) NOT NULL DEFAULT '' AFTER mb_id;

-- 기존 주문은 전부 SQLD 다
UPDATE ex_order SET pd_id = 'sqld' WHERE pd_id = '';

-- 품목별 중복 검사(mb_id + pd_id + od_status)가 쓸 인덱스.
-- 기존 idx_mb (mb_id, created_at) 로는 pd_id 를 못 걸러 풀스캔에 가까워진다.
ALTER TABLE ex_order
  ADD INDEX IF NOT EXISTS idx_mbpd (mb_id, pd_id, od_status);


-- ── 2. ex_plan 에 pd_id ─────────────────────────────────────────────────────
ALTER TABLE ex_plan
  ADD COLUMN IF NOT EXISTS pd_id VARCHAR(20) NOT NULL DEFAULT '' AFTER pl_id;

UPDATE ex_plan SET pd_id = 'sqld' WHERE pd_id = '';

ALTER TABLE ex_plan
  ADD INDEX IF NOT EXISTS idx_pd (pd_id, pl_open, pl_sort);


-- ── 3. ★★ ex_credit_lot — 포인트를 문제집별로 ★★ ──────────────────────────
--
--  이 블록이 이 마이그레이션에서 가장 중요하다. 컬럼만 추가하면 안 된다 —
--  유니크 키를 같이 바꿔야 두 문제집의 같은 달 지급이 둘 다 들어간다.
--
ALTER TABLE ex_credit_lot
  ADD COLUMN IF NOT EXISTS pd_id VARCHAR(20) NOT NULL DEFAULT '' AFTER mb_id;

UPDATE ex_credit_lot SET pd_id = 'sqld' WHERE pd_id = '';

--  기존:  UNIQUE (mb_id, lot_src, lot_period)
--    → 회원 A 가 SQLD·빅분기를 둘 다 수강하면 2026-08 지급이 2건 발생하는데
--      (A,'monthly','2026-08') 이 이미 있어 두 번째가 1062 Duplicate entry 로 거부된다.
--      "왜 한 문제집만 포인트가 들어오지?" — 원인 추적이 매우 어려운 종류의 버그다.
--
--  변경:  UNIQUE (mb_id, pd_id, lot_src, lot_period)
--    → 이중 지급 차단이라는 원래 목적은 그대로다(같은 회원·같은 문제집·같은 달은 1건).
--      PLAN.md §5-1 이 "이 설계에서 가장 놓치기 쉬운 버그"라고 적은 그 제약을 유지한다.
ALTER TABLE ex_credit_lot DROP INDEX IF EXISTS uq_month;
ALTER TABLE ex_credit_lot
  ADD UNIQUE KEY IF NOT EXISTS uq_month (mb_id, pd_id, lot_src, lot_period);

--  잔액 조회가 pd_id 로 걸러지므로 인덱스 선두에 넣는다.
--  ex_credit_balance() 의 WHERE 는 (mb_id, pd_id, lot_expire >= 오늘, lot_used < lot_qty) 다.
ALTER TABLE ex_credit_lot DROP INDEX IF EXISTS idx_bal;
ALTER TABLE ex_credit_lot
  ADD INDEX IF NOT EXISTS idx_bal (mb_id, pd_id, lot_expire, lot_used);

--  ★ lot_period 를 NULL 허용으로 바꾼다 — uq_month 가 관리자 강제 지급을 막는 문제.
--
--    lot_period 는 CHAR(7) 이라 '2026-08' 같은 월 지급분만 담을 수 있고, 그 외
--    (manual · topup · promo · refund) 는 넣을 값이 없어 '' 이 된다. 그런데 '' 은
--    유니크 키에서 **하나의 값**이므로 (회원, 문제집, 'manual', '') 조합이 1건으로 제한된다.
--    → 같은 회원에게 강제 지급을 **두 번 할 수 없다.** 강제 지급은 실운영 경로다
--      (내부 오픈 기간의 지급 방식 자체다. PLAN.md · buy.php 헤더 주석 참조).
--
--    SQL 표준에서 NULL 은 유니크 키 판정에서 **서로 다른 값**으로 취급된다.
--    그래서 월 지급만 'YYYY-MM' 을 넣고 나머지는 NULL 로 두면
--      · monthly  → 같은 달 재지급 차단(원래 목적 그대로)
--      · 그 외    → 몇 번이든 발급 가능
--    이 둘이 한 제약으로 동시에 성립한다. 멱등성은 ex_credit_ledger.lg_ref 로 따로 잡는다.
--
--    ⚠ 이 결함은 원래 스키마에도 있었다. 크레딧 코드가 한 줄도 없어서 드러나지 않았을 뿐이다.
ALTER TABLE ex_credit_lot MODIFY COLUMN lot_period CHAR(7) NULL DEFAULT NULL;
UPDATE ex_credit_lot SET lot_period = NULL WHERE lot_period = '';


-- ── 4. ex_credit_ledger 에 pd_id ────────────────────────────────────────────
--  원장은 append-only 다(UPDATE/DELETE 금지). 컬럼 추가와 과거 행 backfill 은
--  '정정'이 아니라 '누락 정보 보강'이라 이 원칙과 충돌하지 않는다.
ALTER TABLE ex_credit_ledger
  ADD COLUMN IF NOT EXISTS pd_id VARCHAR(20) NOT NULL DEFAULT '' AFTER mb_id;

UPDATE ex_credit_ledger SET pd_id = 'sqld' WHERE pd_id = '';

ALTER TABLE ex_credit_ledger
  ADD INDEX IF NOT EXISTS idx_mbpd (mb_id, pd_id, created_at);


-- ── 5. ex_qna — 하드코딩된 기본값 제거 + 과목게시판 연결 ────────────────────
--  pd_id DEFAULT 'sqld' 는 품목이 하나일 때의 편의였다. 이제는 위험하다 —
--  pd 를 넘기지 않은 INSERT 가 조용히 SQLD 질문이 된다.
ALTER TABLE ex_qna MODIFY COLUMN pd_id VARCHAR(20) NOT NULL DEFAULT '';

--  sj_no = 과목(게시판 말머리).
--  pr_key 가 있으면 ex_problem 조인으로 유도할 수 있지만, 실제 이용 패턴은
--  "무슨 과목 몇 번"을 다 적기보다 **앞을 생략**하는 쪽이다. 과목만 고르고 본문을 쓴다.
--  그래서 유도값이 아니라 명시 컬럼으로 둔다. 0 = 미지정.
ALTER TABLE ex_qna
  ADD COLUMN IF NOT EXISTS sj_no TINYINT NOT NULL DEFAULT 0 AFTER pr_key;

--  그누보드 게시판 글과의 연결.
--  게시판(g5_write_*)을 **화면**으로 쓰고, ex_qna 를 상태·초안·정산의 **원장**으로 쓴다.
--  글쓰기·답글·첨부·검색·권한은 코어가 이미 완성품이라 다시 만들지 않는다.
ALTER TABLE ex_qna
  ADD COLUMN IF NOT EXISTS bo_table VARCHAR(20)  NOT NULL DEFAULT '' AFTER sj_no;
ALTER TABLE ex_qna
  ADD COLUMN IF NOT EXISTS wr_id    INT UNSIGNED NOT NULL DEFAULT 0  AFTER bo_table;

ALTER TABLE ex_qna ADD INDEX IF NOT EXISTS idx_wr (bo_table, wr_id);
ALTER TABLE ex_qna ADD INDEX IF NOT EXISTS idx_sj (pd_id, sj_no, qa_status);

--  누가 답변·반려했는가. 검수 감사에 필요하다 —
--  "이 답변 누가 썼나"에 답할 수 없으면 품질 관리도 책임 추적도 안 된다.
--  ⚠ 콜레이션을 utf8mb3 으로 맞춘다. g5_member.mb_id 가 utf8mb3 이라
--    조인할 때 utf8mb4 와 섞이면 ERROR 1267 이 난다(schema.sql 머리 주석 §콜레이션).
--    ex_problem.edited_by 가 같은 이유로 utf8mb3 이다.
ALTER TABLE ex_qna
  ADD COLUMN IF NOT EXISTS edited_by VARCHAR(20)
      CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci NOT NULL DEFAULT '';
ALTER TABLE ex_qna
  ADD COLUMN IF NOT EXISTS edited_at DATETIME NULL;


-- ── 6. 빅데이터분석기사 필기 품목 추가 ──────────────────────────────────────
--  문제 데이터는 아직 없다. 그래도 지금 넣는 이유:
--  api/products.php 가 "문제 0건이면 pd_open=1 이어도 준비 중" 으로 처리하므로
--  랜딩에 '준비 중' 카드로 뜨고, 신청·마이페이지·포인트 구조를 안전하게 테스트할 수 있다.
--  (이용자가 들어가서 빈 화면을 보는 경로가 원리적으로 없다)
--
--  tier T1 · cost_units 10 은 SQLD 와 같게 뒀다. 필기 객관식이라 토큰 규모가 비슷하다.
--  실측 후 조정한다.
INSERT INTO ex_product
  (pd_id, pd_name, pd_open, tier, model_id, provider, cost_units, cost_cap, pd_sort)
VALUES
  ('bdae-w', '빅데이터분석기사 필기', 1, 'T1', 'deepseek-v4-flash', 'openai_compat', 10, 3.0000, 20)
ON DUPLICATE KEY UPDATE pd_name = VALUES(pd_name), pd_sort = VALUES(pd_sort);


-- ── 7. 빅데이터분석기사 수강 과정 3개 ───────────────────────────────────────
--  ⚠ 가격은 **일단 SQLD 와 동일하게** 넣었다. 문제집별로 분리한 목적이 가격 차등이니
--    정해지면 이 세 줄의 pl_price · pl_quota 만 고쳐 다시 실행하면 된다
--    (ON DUPLICATE KEY UPDATE 라 재실행이 안전하다).
--
--  pl_id 를 11·12·13 으로 명시한다 — AUTO_INCREMENT 에 맡기면 재실행 때 행이 늘어난다.
--  문제집이 늘어나면 10 단위로 띄운다(sqld 1~3, bdae-w 11~13, 다음 21~23).
INSERT INTO ex_plan (pl_id, pd_id, pl_name, pl_price, pl_months, pl_quota, pl_open, pl_sort) VALUES
  (11, 'bdae-w', '1개월 · 매월 질문 100개',   1100, 1,  1000, 1, 10),
  (12, 'bdae-w', '3개월 · 매월 질문 100개',   3000, 3,  1000, 1, 20),
  (13, 'bdae-w', '12개월 · 매월 질문 100개', 11000, 12, 1000, 1, 30)
ON DUPLICATE KEY UPDATE
  pd_id = VALUES(pd_id), pl_name = VALUES(pl_name), pl_price = VALUES(pl_price),
  pl_months = VALUES(pl_months), pl_quota = VALUES(pl_quota), pl_sort = VALUES(pl_sort);


-- ============================================================================
--  검증 — _probe/exam_migrate.php 가 아래를 자동으로 돌린다.
--         phpMyAdmin 에서 직접 확인하려면 그대로 붙여넣는다.
-- ============================================================================
--
-- (1) pd_id 컬럼이 5개 테이블에 생겼는가  → 5행
--   SELECT TABLE_NAME, COLUMN_TYPE FROM information_schema.COLUMNS
--    WHERE TABLE_SCHEMA = DATABASE() AND COLUMN_NAME = 'pd_id'
--      AND TABLE_NAME IN ('ex_order','ex_plan','ex_credit_lot','ex_credit_ledger','ex_qna')
--    ORDER BY TABLE_NAME;
--
-- (2) pd_id 가 빈 행이 남았는가  → 전부 0
--   SELECT (SELECT COUNT(*) FROM ex_order         WHERE pd_id='') AS ord,
--          (SELECT COUNT(*) FROM ex_plan          WHERE pd_id='') AS pln,
--          (SELECT COUNT(*) FROM ex_credit_lot    WHERE pd_id='') AS lot,
--          (SELECT COUNT(*) FROM ex_credit_ledger WHERE pd_id='') AS lgr;
--
-- (3) ★★ 이중 지급 차단 제약이 문제집을 포함하는가  → 4행 · Non_unique = 0
--   SHOW INDEX FROM ex_credit_lot WHERE Key_name = 'uq_month';
--   -- (mb_id, pd_id, lot_src, lot_period) 순서여야 한다.
--   -- 3행이면 옛 키가 그대로다 → 두 번째 문제집 월 지급이 막힌다.
--
-- (4) 문제집별 과정이 갈렸는가  → sqld 3 · bdae-w 3
--   SELECT d.pd_id, d.pd_name, COUNT(p.pl_id) AS plans
--     FROM ex_product d LEFT JOIN ex_plan p ON p.pd_id = d.pd_id AND p.pl_open = 1
--    GROUP BY d.pd_id, d.pd_name ORDER BY d.pd_sort;
--
-- (5) 고아 주문 — 주문의 품목과 그 과정의 품목이 어긋난 것  → 0
--   SELECT COUNT(*) AS orphan FROM ex_order o
--     JOIN ex_plan p ON p.pl_id = o.pl_id
--    WHERE p.pd_id <> o.pd_id;
--
-- (6) ex_qna 신규 컬럼  → 3행 (sj_no, bo_table, wr_id)
--   SELECT COLUMN_NAME, COLUMN_TYPE FROM information_schema.COLUMNS
--    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ex_qna'
--      AND COLUMN_NAME IN ('sj_no','bo_table','wr_id') ORDER BY ORDINAL_POSITION;
-- ============================================================================
