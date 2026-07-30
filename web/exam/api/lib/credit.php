<?php
/**
 * /exam/api/lib/credit.php — 포인트(질문권) 엔진.  **문제집(pd_id)별로 분리된다.**
 *
 * ⚠ 직접 열 수 없다. /exam/.htaccess 의 `RewriteRule ^api/lib/ - [F,L]` 가 막는다.
 *   회원 API(_boot.php 를 거친 것)와 관리자 화면(adm/_common.php 를 거친 것)에서
 *   require_once 로 불러 쓴다. 두 진입점 모두 그누보드 DB 핸들이 열린 상태다.
 *
 * ── 설계 요약 (근거는 _context/PLAN.md §5) ──────────────────────────────────
 *
 *  단위는 **원**이다. 질문 1건 = ex_product.cost_units 원(기본 10). 화면에는 원을 노출하지
 *  않고 floor(잔액 / 단가) 로 환산해 "질문 N개"로 보여준다(COST.md §8).
 *
 *  트랜잭션을 쓰지 않는다. 그누보드 코어가 포인트 차감을 하는 방식 그대로,
 *  **WHERE 절에 사전 검증을 넣은 원자적 UPDATE + affected_rows 판별**로 한다.
 *  insert_use_point() 주석: "affected_rows로 성공/실패를 판별하고 실패 시 재시도하므로
 *  락 없이 무결성 보장." MyISAM/InnoDB 양쪽 호환이고 FOR UPDATE 가 필요 없다.
 *
 *  cron 을 쓰지 않는다. 카페24 공유호스팅은 cron·event_scheduler 를 공식 미지원한다.
 *    · 월 지급 → 조회 시점 정산(ex_settle). 두 달 만에 로그인해도 건너뛴 달을 한 번에 돈다
 *    · 만료   → 잔액 쿼리가 lot_expire >= 오늘 로 거르므로 배치가 아예 필요 없다
 *    · 만료 원장 기록 → lazy. 조회하다 발견하면 그 자리에서 남긴다
 *
 *  이중 지급은 DB 제약이 막는다. UNIQUE (mb_id, pd_id, lot_src, lot_period).
 *  lot_period 는 월 지급만 'YYYY-MM' 이고 나머지는 NULL 이다 —
 *  NULL 은 유니크 판정에서 서로 다른 값이라 강제 지급을 몇 번이든 할 수 있다
 *  (migrate-001 §3 주석 참조). 그쪽 멱등성은 lg_ref 로 따로 잡는다.
 */

if (!defined('_GNUBOARD_')) exit;

/* ── 내부 유틸 ──────────────────────────────────────────────────────────── */

/**
 * 이스케이프 별칭.
 * ⚠ sql_escape_string() 이 아니다 — 그건 사실상 addslashes() 다(GNUBOARD-FACTS §5).
 */
function exc_s($v) { return sql_real_escape_string((string)$v); }

/** 오늘(YYYY-MM-DD). G5_TIME_YMD 는 그누보드가 요청 시작 시각으로 정의한 상수다. */
function exc_today() { return defined('G5_TIME_YMD') ? G5_TIME_YMD : date('Y-m-d'); }

/** 지금(YYYY-MM-DD HH:MM:SS). */
function exc_now() { return defined('G5_TIME_YMDHIS') ? G5_TIME_YMDHIS : date('Y-m-d H:i:s'); }

/**
 * affected_rows. _boot.php 에 이미 있으면 그것을 쓴다.
 * 관리자 화면에서 부를 때는 _boot.php 를 거치지 않으므로 여기서 한 번 더 정의한다.
 * ⚠ 차감의 정확성이 통째로 이 함수에 의존한다(GNUBOARD-FACTS §14-13).
 */
if (!function_exists('ex_affected')) {
    function ex_affected() {
        global $g5;
        if (function_exists('sql_affected_rows')) return (int)sql_affected_rows();
        return (int)mysqli_affected_rows($g5['connect_db']);
    }
}

/**
 * 원장 1행. append-only — 이 테이블은 UPDATE·DELETE 하지 않는다(정정도 새 행).
 *
 * @param string $ref  멱등키. 'qna:1234' · 'order:88' · 'expire:lot:12' 형식.
 * @param int    $bal  기록 시점 잔액 스냅샷(감사용). 호출자가 계산해서 넘긴다.
 */
function exc_ledger($mb, $pd, $lot_id, $type, $amt, $ref, $bal, $by = '', $memo = '') {
    sql_query("insert into ex_credit_ledger
                   (mb_id, pd_id, lot_id, lg_type, lg_amt, lg_ref, lg_bal, lg_by, lg_memo, created_at)
               values ('" . exc_s($mb) . "', '" . exc_s($pd) . "', " . (int)$lot_id . ",
                       '" . exc_s($type) . "', " . (int)$amt . ", '" . exc_s(substr($ref, 0, 40)) . "',
                       " . (int)$bal . ", '" . exc_s(substr($by, 0, 20)) . "',
                       '" . exc_s(mb_substr((string)$memo, 0, 180)) . "', '" . exc_now() . "')", false);
}

/**
 * 이 lg_ref 로 이미 기록된 적이 있는가. 멱등성 판정용.
 * idx_ref (lg_ref) 인덱스가 있다.
 *
 * $type 을 함께 보는 이유: 같은 질문(qna:5)에 debit 과 refund 가 둘 다 남는다.
 * 환불 여부를 물을 때 debit 기록에 걸려 "이미 했다"로 오판하면 안 된다.
 */
function exc_ref_done($ref, $type = '') {
    $w = "lg_ref = '" . exc_s(substr($ref, 0, 40)) . "'";
    if ($type !== '') $w .= " and lg_type = '" . exc_s($type) . "'";
    $r = sql_fetch("select lg_id from ex_credit_ledger where $w limit 1");
    return !empty($r);
}


/* ═══════════════════════════════════════════════════════════════════════════
 *  잔액
 * ═══════════════════════════════════════════════════════════════════════════ */

/**
 * 유효 잔액(원). 만료분은 WHERE 절에서 자동 제외되므로 cron 이 필요 없다.
 *
 * ⚠ lot_expire >= 오늘 은 **당일 포함**이다. 만료일 당일까지 쓸 수 있다는 뜻이고
 *   ex_settle() 이 만료일을 '지급월 말일'로 잡는 것과 짝이 맞는다.
 */
function ex_credit_balance($mb, $pd) {
    if ($mb === '' || $pd === '') return 0;
    $r = sql_fetch("select coalesce(sum(lot_qty - lot_used), 0) as bal
                      from ex_credit_lot
                     where mb_id = '" . exc_s($mb) . "' and pd_id = '" . exc_s($pd) . "'
                       and lot_expire >= '" . exc_today() . "'
                       and lot_used < lot_qty");
    return $r ? (int)$r['bal'] : 0;
}

/** 질문 단가(원). 품목 설정이 없으면 10. */
function ex_credit_unit($pd) {
    $r = sql_fetch("select cost_units from ex_product where pd_id = '" . exc_s($pd) . "'");
    $u = $r ? (int)$r['cost_units'] : 10;
    return $u > 0 ? $u : 10;      // 0 이면 나눗셈이 터진다
}

/** 화면에 쓰는 값 — 남은 질문 개수. 원 단위는 노출하지 않는다. */
function ex_credit_count($mb, $pd) {
    return (int)floor(ex_credit_balance($mb, $pd) / ex_credit_unit($pd));
}


/* ═══════════════════════════════════════════════════════════════════════════
 *  지급
 * ═══════════════════════════════════════════════════════════════════════════ */

/**
 * 포인트 묶음 1건 발급. 월 지급·강제 지급·환불 재발급이 모두 이걸 쓴다.
 *
 * @param string      $src    monthly|topup|promo|manual|refund
 * @param string|null $period 월 지급이면 'YYYY-MM', 그 외는 null (유니크 키 회피)
 * @param string      $expire 'YYYY-MM-DD'. 이 날짜까지 유효(포함)
 * @param string      $ref    원장 멱등키. '' 이면 멱등 검사를 건너뛴다
 * @return int  lot_id. 실패(또는 이미 지급됨)면 0
 */
function ex_credit_grant($mb, $pd, $qty, $src, $period, $expire, $by = '', $memo = '', $ref = '') {
    $qty = (int)$qty;
    if ($mb === '' || $pd === '' || $qty <= 0) return 0;

    // 멱등 — 주문 승인 버튼 두 번 클릭 같은 경로를 여기서 막는다
    if ($ref !== '' && exc_ref_done($ref, 'grant')) return 0;

    $per = ($period === null || $period === '') ? 'NULL' : "'" . exc_s($period) . "'";

    // UNIQUE (mb_id, pd_id, lot_src, lot_period) 위반이면 실패한다 = 이미 그 달에 지급됨.
    // 두 번째 인자 false 로 에러 출력을 끈다 — 이 실패는 정상 흐름이다.
    sql_query("insert into ex_credit_lot
                   (mb_id, pd_id, lot_src, lot_period, lot_qty, lot_used, lot_expire, lot_note, created_at)
               values ('" . exc_s($mb) . "', '" . exc_s($pd) . "', '" . exc_s($src) . "',
                       $per, $qty, 0, '" . exc_s($expire) . "',
                       '" . exc_s(mb_substr((string)$memo, 0, 120)) . "', '" . exc_now() . "')", false);

    if (ex_affected() !== 1) return 0;        // 유니크 위반 = 이미 지급됨. 조용히 넘긴다
    $lot_id = (int)sql_insert_id();
    if (!$lot_id) return 0;

    exc_ledger($mb, $pd, $lot_id, 'grant', +$qty, $ref, ex_credit_balance($mb, $pd), $by, $memo);
    return $lot_id;
}

/**
 * 월 지급(drip) 정산. 조회 시점에 돈다.
 *
 * ex_entitlement 가 원천이다 — 주문 승인이 여기에 1행을 만들고(months_paid 개월),
 * 이 함수가 next_grant_on 이 지난 만큼 lot 을 발급한다.
 *
 * ★ 미사용분 소멸이 자동이다. 만료일을 '지급월의 말일'로 잡으므로
 *   다음 달 잔액 쿼리에서 자동으로 빠진다. 이월되지 않는다는 약관과 일치한다
 *   (buy.php 의 동의 항목 · ex_user_ext.agree_at).
 *
 * ★ 건너뛴 달도 발급한다. 만료일이 이미 과거라 즉시 소멸되지만 **원장에 흔적이 남아**
 *   "왜 없어졌나" 문의에 답할 수 있다. 이게 지급을 건너뛰는 것보다 낫다.
 *
 * @return int 이번에 발급한 건수
 */
function ex_settle($mb, $pd) {
    if ($mb === '' || $pd === '') return 0;
    $mbq = exc_s($mb);
    $pdq = exc_s($pd);
    $today = exc_today();
    $n = 0;

    // guard: 무한 루프 방지. 12개월 결제 + 오래 미접속을 덮고도 남는다.
    for ($guard = 0; $guard < 36; $guard++) {
        $e = sql_fetch("select monthly_quota, months_paid, months_granted, next_grant_on
                          from ex_entitlement
                         where mb_id = '$mbq' and pd_id = '$pdq'");
        if (!$e) break;
        if ((int)$e['months_granted'] >= (int)$e['months_paid']) break;
        if ($e['next_grant_on'] > $today) break;

        $on     = $e['next_grant_on'];                 // 'YYYY-MM-DD'
        $period = substr($on, 0, 7);                   // 'YYYY-MM'

        /* 만료 = 지급일 + 1개월 - 1일 (PLAN.md §5-1).
         *
         * ★ PHP strtotime 을 쓰지 않는다. '2026-01-31 +1 month' 가 **2026-03-03** 이 된다
         *   (2월 31일이 없어서 넘친다). -1 day 를 해도 3월 2일이라 한 달을 더 준다.
         *
         * MariaDB DATE_ADD 는 말일을 클램프한다 — '2026-01-31' + 1 MONTH = '2026-02-28'.
         * 아래 UPDATE 의 date_add(next_grant_on, interval 1 month) 와 **같은 함수**로
         * 계산해야 만료일과 다음 지급일이 어긋나지 않는다. 그래서 DB 에 맡긴다.
         *
         * 왜 '지급월 말일'이 아닌가: 28일에 결제한 회원이 3일 만에 소멸당한다.
         * 지급일 기준 1개월이라야 누가 언제 결제해도 같은 기간을 받는다. */
        $er = sql_fetch("select date_format(
                                 date_sub(date_add('" . exc_s($on) . "', interval 1 month),
                                          interval 1 day), '%Y-%m-%d') as e");
        $expire = ($er && $er['e']) ? $er['e'] : date('Y-m-t', strtotime($period . '-01'));

        ex_credit_grant($mb, $pd, (int)$e['monthly_quota'], 'monthly', $period, $expire,
                        '', $period . ' 월 지급', 'drip:' . $pd . ':' . $period);

        // 지급 성공/실패(이미 있음) 무관하게 커서를 전진시킨다.
        // 실패는 '이미 지급됨'뿐이므로 여기서 멈추면 영원히 같은 달을 재시도한다.
        sql_query("update ex_entitlement
                      set months_granted = months_granted + 1,
                          next_grant_on  = date_add(next_grant_on, interval 1 month),
                          updated_at     = '" . exc_now() . "'
                    where mb_id = '$mbq' and pd_id = '$pdq'
                      and next_grant_on = '" . exc_s($on) . "'", false);
        if (ex_affected() !== 1) break;   // 동시 요청이 이미 전진시켰다 — 그쪽에 맡긴다
        $n++;
    }

    ex_credit_expire_log($mb, $pd);
    return $n;
}

/**
 * 만료 원장 기록 — lazy. 배치가 없으니 조회하는 사람이 남긴다.
 * lot_exp_logged 로 중복을 막는다. 조회 1회당 몇 건이라 부담 없다.
 */
function ex_credit_expire_log($mb, $pd) {
    $res = sql_query("select lot_id, lot_qty - lot_used as rest
                        from ex_credit_lot
                       where mb_id = '" . exc_s($mb) . "' and pd_id = '" . exc_s($pd) . "'
                         and lot_expire < '" . exc_today() . "'
                         and lot_used < lot_qty and lot_exp_logged = 0
                       limit 24", false);
    $lots = array();
    while ($res && $r = sql_fetch_array($res)) $lots[] = $r;

    foreach ($lots as $l) {
        // 먼저 플래그를 세운다. 동시 요청 중 하나만 원장을 남긴다.
        sql_query("update ex_credit_lot set lot_exp_logged = 1
                    where lot_id = " . (int)$l['lot_id'] . " and lot_exp_logged = 0", false);
        if (ex_affected() !== 1) continue;
        exc_ledger($mb, $pd, (int)$l['lot_id'], 'expire', -(int)$l['rest'],
                   'expire:lot:' . (int)$l['lot_id'], ex_credit_balance($mb, $pd), '', '기간 만료 소멸');
    }
}


/* ═══════════════════════════════════════════════════════════════════════════
 *  차감
 * ═══════════════════════════════════════════════════════════════════════════ */

/**
 * $cost 원 차감. 성공하면 true.
 *
 * FIFO — 먼저 만료되는 lot 부터 쓴다(이용자에게 유리하다).
 * 한 번의 차감이 여러 lot 에 걸칠 수 있다.
 *
 * ★ 동시 요청: 잔액 10원인 회원이 [질문하기]를 연타하면 두 요청이 같은 lot 에
 *   `UPDATE ... AND lot_used + 10 <= lot_qty` 를 실행한다. InnoDB 가 행을 잠그고
 *   순차 처리하므로 첫 번째만 affected=1 이고 두 번째는 0 이다. **초과 차감이 불가능하다.**
 *
 * ★ 부분 실패 되돌림: 루프 중간에 잔액이 떨어지면 일부만 빠진 상태가 된다.
 *   그대로 false 를 돌려주면 "포인트는 줄었는데 질문은 없다"가 된다.
 *   그래서 빠진 만큼을 즉시 환불한다. PLAN.md §5-2 가 "이 경로를 반드시 테스트한다"고
 *   경고한 지점이다.
 */
function ex_credit_debit($mb, $pd, $cost, $ref, $memo = '') {
    $cost = (int)$cost;
    if ($mb === '' || $pd === '' || $cost <= 0) return false;

    // 사전 체크. 대부분의 실패를 여기서 걸러 부분 차감 경로에 들어가지 않게 한다.
    if (ex_credit_balance($mb, $pd) < $cost) return false;

    $mbq   = exc_s($mb);
    $pdq   = exc_s($pd);
    $today = exc_today();
    $left  = $cost;

    for ($guard = 0; $guard < 24 && $left > 0; $guard++) {
        $lot = sql_fetch("select lot_id, lot_qty - lot_used as avail
                            from ex_credit_lot
                           where mb_id = '$mbq' and pd_id = '$pdq'
                             and lot_expire >= '$today' and lot_used < lot_qty
                           order by lot_expire asc, lot_id asc limit 1");
        if (!$lot) break;                              // 잔액 소진

        $take = min($left, (int)$lot['avail']);
        if ($take <= 0) break;

        // ★ 원자적 조건부 UPDATE. 동시 요청 중 하나만 성공한다.
        sql_query("update ex_credit_lot set lot_used = lot_used + " . (int)$take . "
                    where lot_id = " . (int)$lot['lot_id'] . "
                      and lot_used + " . (int)$take . " <= lot_qty
                      and lot_expire >= '$today'", false);

        if (ex_affected() === 1) {
            $left -= $take;
            exc_ledger($mb, $pd, (int)$lot['lot_id'], 'debit', -$take, $ref,
                       ex_credit_balance($mb, $pd), '', $memo);
        }
        // affected = 0 → 경쟁에서 졌다. 루프가 다음 lot(또는 갱신된 같은 lot)을 다시 읽는다.
    }

    if ($left === 0) return true;

    // 부분 차감 되돌림. 여기까지 왔다면 사전 체크 이후에 잔액이 사라진 경우다.
    $taken = $cost - $left;
    if ($taken > 0) {
        ex_credit_refund($mb, $pd, $taken, $ref . ':rollback', '부분 차감 되돌림', '', true);
    }
    return false;
}


/* ═══════════════════════════════════════════════════════════════════════════
 *  환불
 * ═══════════════════════════════════════════════════════════════════════════ */

/**
 * $amt 원 환불. 질문 반려 시 돌려준다.
 *
 * 없으면 "돈 냈는데 답이 없다" 민원이 생긴다. 반드시 있어야 하는 경로다(PLAN.md §5-4).
 *
 * 원래 쓴 lot 을 되돌리는 것을 우선한다(그쪽이 만료일을 보존한다).
 * 그 lot 이 이미 만료됐으면 되돌려도 못 쓰므로 **새 lot(lot_src='refund')을 발급**한다.
 *
 * @param bool $force  true 면 멱등 검사를 건너뛴다(부분 차감 되돌림 전용).
 * @return bool
 */
function ex_credit_refund($mb, $pd, $amt, $ref, $memo = '', $by = '', $force = false) {
    $amt = (int)$amt;
    if ($mb === '' || $pd === '' || $amt <= 0) return false;

    if (!$force && $ref !== '' && exc_ref_done($ref, 'refund')) return false;   // 중복 환불 방지

    $mbq   = exc_s($mb);
    $pdq   = exc_s($pd);
    $today = exc_today();
    $left  = $amt;

    // ① 아직 유효한 lot 중 쓴 흔적이 있는 것을 되돌린다. 늦게 만료되는 것부터 —
    //    빨리 만료될 lot 을 되돌려주면 되돌린 즉시 소멸할 수 있어 이용자에게 불리하다.
    for ($guard = 0; $guard < 24 && $left > 0; $guard++) {
        $lot = sql_fetch("select lot_id, lot_used from ex_credit_lot
                           where mb_id = '$mbq' and pd_id = '$pdq'
                             and lot_expire >= '$today' and lot_used > 0
                           order by lot_expire desc, lot_id desc limit 1");
        if (!$lot) break;

        $give = min($left, (int)$lot['lot_used']);
        if ($give <= 0) break;

        sql_query("update ex_credit_lot set lot_used = lot_used - " . (int)$give . "
                    where lot_id = " . (int)$lot['lot_id'] . "
                      and lot_used >= " . (int)$give, false);

        if (ex_affected() === 1) {
            $left -= $give;
            exc_ledger($mb, $pd, (int)$lot['lot_id'], 'refund', +$give, $ref,
                       ex_credit_balance($mb, $pd), $by, $memo);
        }
    }

    // ② 되돌릴 곳이 없으면(원 lot 이 만료됨) 새 lot 을 발급한다. 만료는 30일.
    if ($left > 0) {
        $expire = date('Y-m-d', strtotime($today . ' +30 days'));
        // lot_period = null → uq_month 에 걸리지 않으므로 몇 번이든 발급된다.
        // ref 를 넘기지 않는다 — 위 ①에서 이미 같은 ref 로 원장을 남겼을 수 있고,
        // grant 의 멱등 검사(lg_type='grant')와 종류가 달라 충돌하지도 않는다.
        $lot_id = ex_credit_grant($mb, $pd, $left, 'refund', null, $expire, $by,
                                  $memo !== '' ? $memo : '반려 환불 (원 지급분 만료)');
        if ($lot_id) $left = 0;
    }

    return $left === 0;
}


/* ═══════════════════════════════════════════════════════════════════════════
 *  주문 승인 → 구독권 + 첫 달 지급
 * ═══════════════════════════════════════════════════════════════════════════ */

/**
 * 주문을 승인한다. adm/exam_orders.php 가 부른다.
 *
 * ★ 멱등이다. 'order:<od_id>' 를 원장 키로 쓰므로 버튼을 두 번 눌러도 한 번만 지급된다.
 *   운영 화면에서 가장 흔한 사고(중복 클릭)를 여기서 원리적으로 막는다.
 *
 * 순서: od_status 를 먼저 paid 로 바꾸고(조건부) → 구독권 → 지급.
 * 상태 변경을 조건부 UPDATE 로 하면 동시 클릭 중 하나만 통과한다.
 *
 * @return array {ok, msg, granted}
 */
function ex_order_approve($od_id, $by = '') {
    $od_id = (int)$od_id;
    if ($od_id <= 0) return array('ok' => 0, 'msg' => '주문번호가 없습니다.', 'granted' => 0);

    $o = sql_fetch("select * from ex_order where od_id = $od_id");
    if (!$o) return array('ok' => 0, 'msg' => '주문을 찾을 수 없습니다.', 'granted' => 0);

    $mb = (string)$o['mb_id'];
    $pd = (string)$o['pd_id'];
    if ($pd === '') return array('ok' => 0, 'msg' => '주문에 문제집이 지정되지 않았습니다. 마이그레이션을 확인하십시오.', 'granted' => 0);

    // ★ 조건부 상태 변경 — pending 인 것만 통과한다. 동시 클릭 방어.
    sql_query("update ex_order set od_status = 'paid', paid_at = '" . exc_now() . "'
                where od_id = $od_id and od_status = 'pending'", false);
    if (ex_affected() !== 1) {
        return array('ok' => 0, 'msg' => '이미 처리된 주문입니다(상태: ' . $o['od_status'] . ').', 'granted' => 0);
    }

    $months = max(1, (int)$o['od_months']);
    $quota  = max(0, (int)$o['od_quota']);
    $today  = exc_today();

    /* 구독권 = 월 지급의 원천. PRIMARY KEY (mb_id, pd_id) 라 문제집별로 1행이다.
     *
     * 이미 있으면(연장 결제) months_paid 를 더한다 — months_granted 는 건드리지 않는다.
     * 그래야 ex_settle 이 "아직 안 준 개월"을 정확히 안다.
     * next_grant_on 은 이미 있으면 유지한다. 덮으면 지급 주기가 밀린다. */
    $ex = sql_fetch("select mb_id from ex_entitlement
                      where mb_id = '" . exc_s($mb) . "' and pd_id = '" . exc_s($pd) . "'");
    if ($ex) {
        sql_query("update ex_entitlement
                      set monthly_quota = " . $quota . ",
                          months_paid   = months_paid + " . $months . ",
                          od_id         = $od_id,
                          updated_at    = '" . exc_now() . "'
                    where mb_id = '" . exc_s($mb) . "' and pd_id = '" . exc_s($pd) . "'", false);
    } else {
        sql_query("insert into ex_entitlement
                       (mb_id, pd_id, monthly_quota, months_paid, months_granted,
                        next_grant_on, started_on, od_id, updated_at)
                   values ('" . exc_s($mb) . "', '" . exc_s($pd) . "', " . $quota . ",
                           " . $months . ", 0, '" . $today . "', '" . $today . "',
                           $od_id, '" . exc_now() . "')", false);
    }

    // 첫 달(그리고 밀린 달)을 즉시 지급한다. 승인 직후 바로 쓸 수 있어야 한다.
    $n = ex_settle($mb, $pd);

    return array('ok' => 1, 'granted' => $n,
                 'msg' => '승인했습니다. 월 지급 ' . $n . '건이 반영되었습니다.');
}


/* ═══════════════════════════════════════════════════════════════════════════
 *  정합성 검증 — 관리자 화면 상단 1줄 (PLAN.md §5-6)
 * ═══════════════════════════════════════════════════════════════════════════ */

/**
 * 원장 합계와 lot 잔액이 맞는가.
 *
 * 원장은 append-only 라 언제든 대조할 수 있다.
 * grant(+) · debit(-) · refund(+) · expire(-) 를 모두 더하면 유효 잔액과 같아야 한다.
 *
 * ⚠ 만료 원장이 lazy 라 **아무도 조회하지 않은 만료분은 원장에 아직 없다.**
 *   그래서 ledger_sum 이 lot_avail 보다 클 수 있고, 그건 오류가 아니다.
 *   차이를 pending_expire 로 따로 계산해 화면에서 구분한다.
 */
function ex_credit_audit($pd = '') {
    $w = $pd !== '' ? " where pd_id = '" . exc_s($pd) . "'" : '';
    $today = exc_today();

    $l = sql_fetch("select coalesce(sum(lg_amt), 0) as s from ex_credit_ledger" . $w);
    $a = sql_fetch("select coalesce(sum(lot_qty - lot_used), 0) as s from ex_credit_lot"
                 . ($w === '' ? " where" : $w . " and")
                 . " lot_expire >= '$today' and lot_used < lot_qty");
    // 만료됐지만 아직 원장에 안 남은 잔량
    $p = sql_fetch("select coalesce(sum(lot_qty - lot_used), 0) as s from ex_credit_lot"
                 . ($w === '' ? " where" : $w . " and")
                 . " lot_expire < '$today' and lot_used < lot_qty and lot_exp_logged = 0");

    $ledger  = (int)$l['s'];
    $avail   = (int)$a['s'];
    $pending = (int)$p['s'];

    return array(
        'ledger'  => $ledger,
        'avail'   => $avail,
        'pending' => $pending,
        // 미기록 만료분을 빼면 일치해야 한다
        'ok'      => (($ledger - $pending) === $avail),
    );
}
