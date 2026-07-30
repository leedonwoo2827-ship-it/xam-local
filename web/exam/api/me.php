<?php
/**
 * GET /exam/api/me.php[?pd=sqld]
 *
 * 내 상태 + CSRF 토큰. 화면 부팅 때 가장 먼저 부른다.
 *
 * 반환하는 것
 *   · 로그인 여부 · 닉 · 관리자 여부 · csrf
 *   · books[]  — **내 문제집 목록**. 마이페이지의 문제집 선택 UI 가 이걸로 그려진다
 *   · 선택된 문제집(?pd=)의 포인트 잔액. pd 를 안 주면 books[0] 기준
 *
 * ⚠ 화면에는 `count`(질문 개수)만 쓴다. 차감 단가(원)는 노출하지 않는다 — COST.md §8.
 *   bal/unit 을 같이 주는 것은 디버깅과 관리자 화면용이다.
 *
 * ⚠ ex_settle() 을 여기서 돌린다. cron 이 없으므로 **조회하는 사람이 정산한다.**
 *   카페24 공유호스팅은 cron·event_scheduler 를 공식 미지원한다(HOSTING.md).
 */
require_once __DIR__ . '/_boot.php';
require_once __DIR__ . '/lib/credit.php';

$mb = ex_mb();

if ($mb === '') {
    // 비로그인도 csrf 는 준다 — 익명 채점 경로에서 같은 코드를 쓰기 때문이다.
    ex_out(array(
        'ok'    => 1,
        'login' => 0,
        'csrf'  => ex_csrf(),
        'bal'   => 0,
        'count' => 0,
        'books' => array(),
    ));
}

global $member;
$ext = ex_ext($mb);   // 없으면 생성

/* ── 내 문제집 목록 ─────────────────────────────────────────────────────────
 *
 * "신청했거나 이용 중인 문제집"을 모은다. 두 곳에서 온다:
 *   · ex_order       — 신청 이력(pending 도 보여준다. "접수됨"을 알려줘야 한다)
 *   · ex_entitlement — 승인된 구독권
 *
 * 문제집 이름·노출 여부는 ex_product 가 기준이다. LEFT JOIN 이 아니라 ex_product 를
 * 축으로 도는 이유: 삭제된 품목의 옛 주문이 이름 없이 뜨는 것을 막는다.
 *
 * 정렬은 pd_sort — 랜딩 카드 순서와 같게 보여야 이용자가 헷갈리지 않는다.
 */
$books = array();
$res = sql_query(
    "select d.pd_id, d.pd_name, d.pd_open, d.cost_units,
            (select od_status from ex_order o
              where o.mb_id = '" . sql_real_escape_string($mb) . "' and o.pd_id = d.pd_id
              order by o.od_id desc limit 1)                        as od_status,
            (select created_at from ex_order o
              where o.mb_id = '" . sql_real_escape_string($mb) . "' and o.pd_id = d.pd_id
              order by o.od_id desc limit 1)                        as od_at,
            (select count(*) from ex_entitlement e
              where e.mb_id = '" . sql_real_escape_string($mb) . "' and e.pd_id = d.pd_id) as entitled,
            (select count(*) from ex_problem x
              where x.pd_id = d.pd_id and x.pr_open = 1)            as problems
       from ex_product d
      order by d.pd_sort, d.pd_id", false);

while ($r = sql_fetch_array($res)) {
    $pd       = $r['pd_id'];
    $entitled = (int)$r['entitled'] > 0;
    $status   = $r['od_status'] ? (string)$r['od_status'] : '';

    // 신청도 안 했고 구독권도 없으면 '내 문제집'이 아니다 — 목록에서 뺀다.
    // 랜딩(/exam/)에서 새로 신청하는 경로가 따로 있다.
    if ($status === '' && !$entitled) continue;

    // 승인된 문제집만 정산·잔액 조회를 한다. pending 은 아직 지급 대상이 아니다.
    if ($entitled) ex_settle($mb, $pd);

    $unit = (int)$r['cost_units'] > 0 ? (int)$r['cost_units'] : 10;
    $bal  = $entitled ? ex_credit_balance($mb, $pd) : 0;

    $books[] = array(
        'pd_id'    => $pd,
        'pd_name'  => $r['pd_name'],
        'open'     => ((int)$r['pd_open'] === 1 && (int)$r['problems'] > 0) ? 1 : 0,
        'problems' => (int)$r['problems'],
        'status'   => $status,            // '' | pending | paid | canceled | refunded
        'applied'  => $r['od_at'],
        'entitled' => $entitled ? 1 : 0,
        'bal'      => $bal,
        'count'    => (int)floor($bal / $unit),
    );
}

/* ── 선택된 문제집 ──────────────────────────────────────────────────────────
 * ?pd= 가 내 목록에 있으면 그것, 없으면 첫 번째.
 * 목록에 없는 pd 를 그대로 받아주면 남의 문제집 잔액을 조회하는 셈이 되므로 검증한다.
 */
$want = isset($_GET['pd']) ? ex_pd($_GET['pd'], '') : '';
$sel  = null;
foreach ($books as $b) {
    if ($want !== '' && $b['pd_id'] === $want) { $sel = $b; break; }
}
if ($sel === null && $books) $sel = $books[0];

ex_out(array(
    'ok'      => 1,
    'login'   => 1,
    'mb_id'   => $mb,
    'nick'    => isset($member['mb_nick']) ? $member['mb_nick'] : $mb,
    'admin'   => ex_is_admin() ? 1 : 0,
    'csrf'    => ex_csrf(),

    'books'   => $books,
    'pd'      => $sel ? $sel['pd_id'] : '',

    // 선택된 문제집 기준. 문제집이 없으면 0 — "무료 기간"이 아니라 "신청 없음"이다.
    'bal'     => $sel ? $sel['bal']   : 0,
    'count'   => $sel ? $sel['count'] : 0,
    'unit'    => $sel ? ex_credit_unit($sel['pd_id']) : 10,

    'agreed'  => !empty($ext['agree_at']) ? 1 : 0,
    'blocked' => !empty($ext['blocked'])  ? 1 : 0,
));
