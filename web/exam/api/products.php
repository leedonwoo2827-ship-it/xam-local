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

/* 카드 썸네일·아이콘은 콘텐츠가 아니라 표현이라 DB 에 두지 않는다.
 *
 * ⚠ 이 맵에 품목을 **추가하지 않는다.** 여기에 pd_id 를 적기 시작하면
 *   "품목 추가 = DB 1행" 이라는 원칙이 깨지고, 형제 사이트로 복사할 때도 고쳐야 한다.
 *   모르는 품목은 아래 $skin 계산이 순번으로 색을 돌려준다(pd-t1~t4).
 *   특정 품목의 색·아이콘을 지정하고 싶으면 ex_product.pd_config 에
 *   {"thumb":"pd-t2","icon":"i-chart"} 를 넣는다 — DB 에서 끝난다.
 */
$SKIN_N = 4;                       // pd-t1 ~ pd-t4
$ICONS  = array('i-cpu', 'i-chart', 'i-doc', 'i-calculator');

$items = array();
$res = sql_query("select pd_id, pd_name, pd_open, pd_sort, pd_config from ex_product
                   order by pd_open desc, pd_sort, pd_id", false);

$idx = 0;
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

    /* 표현값 — pd_config 가 있으면 그것, 없으면 순번으로 돌린다.
       하드코딩 맵을 없앤 이유는 위 주석에 있다. */
    $cfg   = ex_unjson($r['pd_config'], array());
    $thumb = (is_array($cfg) && !empty($cfg['thumb'])) ? $cfg['thumb'] : 'pd-t' . (($idx % $SKIN_N) + 1);
    $icon  = (is_array($cfg) && !empty($cfg['icon']))  ? $cfg['icon']  : $ICONS[$idx % count($ICONS)];
    $idx++;

    $items[] = array(
        'pd_id'    => $pd,
        'name'     => $r['pd_name'],
        'open'     => $open ? 1 : 0,
        'problems' => $n,
        'rounds'   => $rd,
        'desc'     => $open
            ? "모의고사 {$rd}회차 · 정답과 해설 전문 포함"
            : '준비 중입니다.',
        'thumb'    => $thumb,
        'icon'     => $icon,
        /* href  = 문제집 상세(기획서 IA 의 중간 단계)
         * solve = 바로 문제풀이
         * 예전에는 href 가 check.html 을 가리키는데 랜딩은 sqld.html 로 링크해서
         * 둘이 조용히 어긋나 있었다. 이제 목적지가 데이터로 정해진다. */
        'href'     => $open ? ('detail.html?pd=' . rawurlencode($pd)) : '',
        'solve'    => $open ? ('check.php?pd='   . rawurlencode($pd)) : '',
    );
}

ex_out(array('ok' => 1, 'items' => $items));
