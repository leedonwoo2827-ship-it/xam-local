<?php
/**
 * GET /exam/api/products.php
 *
 * 포털 랜딩의 자격증 카드용. `ex_product` 를 그대로 돌려준다.
 *
 * 랜딩에 자격증을 하드코딩하지 않는 이유: ADSP 를 추가할 때 랜딩 HTML 을 다시 만지게 된다.
 * 여기서 읽으면 `ex_product` 에 1행 추가 + 문제 임포트로 끝난다(PLAN §4 "PHP 코드 변경 0").
 *
 * 비로그인도 볼 수 있어야 한다 — 랜딩은 공개 페이지다.
 */
require_once __DIR__ . '/_boot.php';

// 카드 썸네일/아이콘은 콘텐츠가 아니라 표현이라 DB 에 두지 않는다.
// pd_id 로 매핑하고, 모르는 품목은 1번 스타일로 떨어뜨린다.
$SKIN = array(
    'sqld'   => array('pd-t1', 'i-cpu'),
    'adsp'   => array('pd-t2', 'i-chart'),
    'gisa-w' => array('pd-t3', 'i-doc'),
    'gisa-p' => array('pd-t3', 'i-edit'),
    'comp'   => array('pd-t4', 'i-calculator'),
);

$items = array();
$res = sql_query("select pd_id, pd_name, pd_open, pd_sort from ex_product
                   order by pd_open desc, pd_sort, pd_id", false);

while ($r = sql_fetch_array($res)) {
    $pd  = $r['pd_id'];
    $pdq = sql_real_escape_string($pd);

    // 노출 중인 문제 수와 회차 수 — 카드에 "300문제 · 6회차" 로 쓴다
    $c = sql_fetch("select count(*) as n, count(distinct rd_no) as rd
                      from ex_problem where pd_id = '$pdq' and pr_open = 1");
    $n  = (int)$c['n'];
    $rd = (int)$c['rd'];

    // 문제가 0건이면 pd_open 이 1이어도 '준비 중'이다 —
    // 열려 있다고 표시했는데 들어가서 빈 화면을 보는 게 최악이다.
    $open = ((int)$r['pd_open'] === 1 && $n > 0);

    $skin = isset($SKIN[$pd]) ? $SKIN[$pd] : array('pd-t1', 'i-clipboard');

    $items[] = array(
        'pd_id'    => $pd,
        'name'     => $r['pd_name'],
        'open'     => $open ? 1 : 0,
        'problems' => $n,
        'rounds'   => $rd,
        'desc'     => $open
            ? "자사 모의고사 {$rd}회차 · 정답과 해설 전문 포함"
            : '준비 중입니다.',
        'thumb'    => $skin[0],
        'icon'     => $skin[1],
        'href'     => $open ? ('check.html?pd=' . rawurlencode($pd)) : '',
    );
}

ex_out(array('ok' => 1, 'items' => $items));
