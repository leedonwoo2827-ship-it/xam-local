-- ============================================================================
--  master.sql — 초기 마스터 데이터
--  schema.sql 을 먼저 실행한 뒤 phpMyAdmin SQL 탭에 붙여넣는다.
--  ex_round / ex_problem 은 여기서 넣지 않는다 — adm/exam_import.php 가 채운다.
-- ============================================================================

SET NAMES utf8mb4;


-- ── 품목 ────────────────────────────────────────────────────────────────────
--  cost_units = 질문 1건당 차감액(원). 실제 LLM 원가는 0.44~0.78원이라 마진 12~23배.
--  이 배수는 LLM 원가가 아니라 **관리자 검수 노동**을 덮기 위한 것이다
--  (검수 1건 2분 = 시급 2만원 환산 667원. LLM 의 850배).
--
--  cost_cap = 건당 원가 경고 상한. 초과하면 검수 화면에 경고가 뜬다.
--  모델을 잘못 바꿔 조용히 적자가 나는 것을 막는 장치다.
--
--  ⚠ 모델 ID: 레거시 deepseek-chat / deepseek-reasoner 는 2026-07-24 폐지됐다.
INSERT INTO ex_product
  (pd_id, pd_name, pd_open, tier, model_id, provider, cost_units, cost_cap, pd_sort)
VALUES
  ('sqld', 'SQL 개발자(SQLD)', 1, 'T1', 'deepseek-v4-flash', 'openai_compat', 10, 3.0000, 10)
ON DUPLICATE KEY UPDATE pd_name = VALUES(pd_name);

-- 나머지 자격증은 문제 데이터가 준비되면 행만 추가한다. PHP 코드 변경 0.
--   ('adsp',   '데이터분석 준전문가(ADSP)', ...)
--   ('gisa-w', '정보처리기사 필기',        ...)
-- ⚠ 실기(gisa-p, comp 실기)는 객관식이 아니라서 문제 데이터 제작부터 다시 해야 한다.
--   모델 티어 문제가 아니라 콘텐츠 문제다. cost_units 도 30원 선으로 다르다.


-- ── 판매 상품 ───────────────────────────────────────────────────────────────
--  pl_quota 는 **월 지급액(원)**이다. 1000원 = 질문 100건(단가 10원 기준).
--  화면에는 원 단위를 노출하지 않고 floor(잔액/단가) 로 환산해 "질문 N개"로 보여준다.
--
--  선결제(3·12개월)는 수수료를 1원도 줄이지 않는다(순수 % 구조).
--  그래도 기본값으로 노출하는 이유는 **갱신 실패 이탈 지점이 연 12회 → 1~4회**로 줄기 때문이다.
--  1,100원 구독의 최대 손실 요인은 수수료가 아니라 카드 만료·한도 초과다.
--
--  ⚠ 질문권은 pool 이 아니라 **월 단위 drip** 이다. 3개월 결제 = 150개 한 번이 아니라
--    월 50개씩 3번이고 매월 미사용분은 소멸한다(ex_entitlement 가 관리).
--    이 설계가 전자상거래법 에스크로 예외("일정기간에 걸쳐 분할되어 공급되는 재화등")에도
--    정확히 부합한다.
INSERT INTO ex_plan (pl_id, pl_name, pl_price, pl_months, pl_quota, pl_open, pl_sort) VALUES
  (1, '1개월 · 매월 질문 100개',   1100, 1,  1000, 1, 10),
  (2, '3개월 · 매월 질문 100개',   3000, 3,  1000, 1, 20),
  (3, '12개월 · 매월 질문 100개', 11000, 12, 1000, 1, 30)
ON DUPLICATE KEY UPDATE
  pl_name = VALUES(pl_name), pl_price = VALUES(pl_price),
  pl_months = VALUES(pl_months), pl_quota = VALUES(pl_quota);


-- ============================================================================
--  검증
-- ============================================================================
--   SELECT pd_id, pd_name, tier, model_id, cost_units, cost_cap FROM ex_product;
--   SELECT pl_id, pl_name, pl_price, pl_months, pl_quota FROM ex_plan ORDER BY pl_sort;
--
--   -- 1,100원 = 질문 100개가 맞는지 (단가 10원)
--   SELECT p.pl_name, p.pl_price, p.pl_quota,
--          FLOOR(p.pl_quota / d.cost_units) AS 월_질문개수
--     FROM ex_plan p CROSS JOIN ex_product d
--    WHERE d.pd_id = 'sqld' ORDER BY p.pl_sort;
-- ============================================================================
