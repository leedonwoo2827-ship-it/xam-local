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
/* ★ `pd_open = 0` 인 품목은 **목록에서 뺀다.**
 *
 *   예전에는 전 행을 돌면서 `open` 플래그만 계산했다. 그래서 관리자가 품목을 숨겨도
 *   랜딩에 회색 '준비 중' 카드가 그대로 남았다 — 실제로 같은 이름의 옛 품목(bdae-w)을
 *   숨겼는데 카드가 두 개로 보였다. 숨김의 뜻은 "안 보이게" 다.
 *
 *   두 상태를 구분해야 한다:
 *     pd_open = 0            → 관리자가 감췄다. 목록에 없다.
 *     pd_open = 1 · 문항 0   → 열어뒀지만 아직 비었다. '준비 중' 으로 **보여준다**
 *                              (아래 $open 판정). 열려 있다고 해놓고 빈 화면을 보는 것보다 낫다.
 *
 *   마이페이지(api/me.php)는 이걸 따르지 않는다 — 거기서는 숨긴 품목도 남아야 한다.
 *   이미 신청·구독한 회원의 이력이 이름 없이 사라지면 안 되기 때문이다.
 *   구매(buy.php)는 자체적으로 `pd_open = 1` 을 걸러 이미 막힌다.
 */
$res = sql_query("select pd_id, pd_name, pd_open, pd_sort, pd_config from ex_product
                  where pd_open = 1
                  order by pd_sort, pd_id", false);

$idx = 0;
while ($r = sql_fetch_array($res)) {
    $pd  = $r['pd_id'];
    $pdq = sql_real_escape_string($pd);

    // 노출 중인 문제 수와 회차 수 — 카드에 "300문제 · 6회차" 로 쓴다
    $c = sql_fetch("select count(*) as n, count(distinct rd_no) as rd
                      from ex_problem where pd_id = '$pdq' and pr_open = 1");
    $n  = (int)$c['n'];
    $rd = (int)$c['rd'];

    /* 과목 수 — 랜딩 스탯이 쓴다. 상수로 두면 자격증마다 틀린다(SQLD 2 · 빅분기 4). */
    $s = sql_fetch("select count(distinct sj_no) as n
                      from ex_problem where pd_id = '$pdq' and pr_open = 1 and sj_no > 0");
    $sj = (int)$s['n'];

    /* ★ 해설 영상 수 — DB 에 없다. 영상은 파일 기반이라 여기서 센다.
     *
     *   videos.js          공개 영상 (min_level <= 1)
     *   videos.private.json 레벨 제한 영상 (min_level >= 2) — 브라우저가 못 읽는다
     *
     *   둘을 합쳐야 실제 편수가 나온다. 빅분기는 전부 min_level 5 라서
     *   videos.js 가 `{}` 이고, 브라우저에서 세면 0 편으로 보인다 — 그래서 서버에서 센다.
     *   구조는 { "1회": [ {...}, ... ], ... } 이므로 값 배열의 길이를 더한다.
     */
    $vid = 0;
    $vbase = G5_PATH . '/exam/pd/' . basename($pd);
    foreach (array('/videos.private.json', '/videos.js') as $vf) {
        $vp = $vbase . $vf;
        if (!is_file($vp)) continue;
        $raw = (string)file_get_contents($vp);
        // videos.js 는 `window.VIDEOS = {...};` 이라 앞뒤를 벗긴다.
        if (substr($vf, -3) === '.js') {
            $b = strpos($raw, '{');
            $e = strrpos($raw, '}');
            $raw = ($b !== false && $e !== false && $e > $b) ? substr($raw, $b, $e - $b + 1) : '';
        }
        $vj = json_decode($raw, true);
        if (is_array($vj)) {
            foreach ($vj as $arr) {
                if (is_array($arr)) $vid += count($arr);
            }
        }
    }

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
        'subjects' => $sj,     // 과목 수 — 랜딩 스탯
        'videos'   => $vid,    // 해설 영상 편수 (공개 + 레벨제한 합계)
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
