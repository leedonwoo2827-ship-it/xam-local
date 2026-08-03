<?php
/**
 * GET /exam/api/board.php?pd=sqld[&sj=2][&n=10]
 *
 * 과목게시판 요약 — check.php 의 넷째 탭이 쓴다.
 *
 * 설계
 *   · 게시판은 **문제집당 1개**다. 과목별로 쪼개지 않고 말머리(bo_category_list)로 나눈다.
 *     과목별로 쪼개면 품목 5개 × 과목 4개 = 20개 게시판이 되고 아무도 관리하지 못한다.
 *   · 게시판 자체는 **운영자가 그누보드 기본 화면에서 만든다.** 우리가 자동 생성하지 않는다 —
 *     g5_board 는 컬럼이 90개가 넘고 권한·스킨·업로드 정책이 다 거기 있다.
 *     대신 말머리는 adm/exam_board_sync.php 가 ex_problem 의 과목 목록에서 맞춘다
 *     (과목명 오타 하나로 필터가 조용히 깨지는 것을 사람이 잡기 어렵다).
 *   · 정본은 게시판이고 이건 요약 뷰다. 페이징·글쓰기·검색은 그누보드로 넘긴다.
 *
 * ⚠ 목록은 비로그인도 본다. 공개 Q&A 가 쌓이는 것이 신규 방문자에게 보여야
 *   유료 전환으로 이어진다(그게 이 게시판의 목적이다).
 *   글쓰기 권한은 그누보드 게시판 설정이 판단한다 — 여기서 흉내내지 않는다.
 */
require_once __DIR__ . '/_boot.php';

$pd = ex_pd(isset($_GET['pd']) ? $_GET['pd'] : '', '');
$sj = isset($_GET['sj']) ? (int)$_GET['sj'] : 0;      // 0 = 전 과목
$n  = isset($_GET['n'])  ? (int)$_GET['n']  : 10;
if ($n < 1 || $n > 30) $n = 10;

if ($pd === '') ex_fail('pd_required');

$prod = sql_fetch("select pd_id, pd_name from ex_product
                    where pd_id = '" . sql_real_escape_string($pd) . "' and pd_open = 1");
if (!$prod) ex_fail('no_such_product', 404);

/**
 * 문제집 → 게시판 테이블명.
 *
 * bo_table 은 영문·숫자·_ 만 쓸 수 있고 20자 제한이다. pd_id 에는 하이픈이 들어간다
 * ('bdae-w') → '_' 로 바꾼다. 접미사 '_sj' 는 과목게시판이라는 뜻이다.
 *   sqld    → sqld_sj
 *   bdae-w  → bdae_w_sj
 *
 * ⚠ 규칙을 바꾸면 이미 만들어둔 게시판을 못 찾는다. adm/exam_board_sync.php 와
 *   같은 함수를 쓰지 않고 양쪽에 같은 규칙을 둔 이유: api/lib/ 는 관리자에서 부르기 번거롭고,
 *   이 함수는 세 줄이라 중복이 싸다. 규칙을 바꿀 때 두 곳을 같이 고친다.
 */
function ex_board_table($pd_id) {
    $t = preg_replace('/[^a-z0-9_]/', '_', strtolower((string)$pd_id));
    return substr($t . '_sj', 0, 20);
}

$bo = ex_board_table($pd);
$boq = sql_real_escape_string($bo);

$board = sql_fetch("select bo_table, bo_subject, bo_category_list, bo_use_category
                      from " . $g5['board_table'] . " where bo_table = '$boq'");

if (!$board) {
    // 게시판이 아직 없다. 화면은 이걸 받아 "게시판이 만들어지지 않았습니다"를 띄운다.
    ex_out(array(
        'ok'        => 0,
        'err'       => 'no_board',
        'pd'        => $pd,
        'bo_table'  => $bo,
        'board_url' => '',
    ));
}

/* 말머리 목록 — 그누보드는 '가|나|다' 형태로 저장한다. */
$cats = array();
if (!empty($board['bo_category_list'])) {
    foreach (explode('|', $board['bo_category_list']) as $c) {
        $c = trim($c);
        if ($c !== '') $cats[] = $c;
    }
}

/* 과목 번호 → 말머리 문자열.
 * 말머리를 과목명으로 맞춰뒀으므로(exam_board_sync.php) sj_name 으로 필터한다.
 * 번호가 아니라 이름으로 거는 이유: 그누보드가 wr_1 같은 여분 컬럼이 아니라
 * wr_category 에 **문자열**을 저장하기 때문이다. */
$cat = '';
if ($sj > 0) {
    $s = sql_fetch("select sj_name from ex_problem
                     where pd_id = '" . sql_real_escape_string($pd) . "'
                       and sj_no = " . $sj . " and sj_name <> '' limit 1");
    if ($s) $cat = $s['sj_name'];
}

$wt = $g5['write_prefix'] . $bo;      // g5_write_sqld_sj

$w = array('wr_is_comment = 0');
if ($cat !== '') $w[] = "wr_category = '" . sql_real_escape_string($cat) . "'";
$where = implode(' and ', $w);

$items = array();
$res = sql_query("select wr_id, wr_subject, wr_name, wr_category, wr_comment,
                         wr_datetime, wr_reply, mb_id
                    from $wt
                   where $where
                   order by wr_num, wr_reply
                   limit " . (int)$n, false);
while ($res && $r = sql_fetch_array($res)) {
    /* '답변완료' 판정: 우리 원장(ex_qna)이 approved 인가.
     * 게시판의 댓글 수로 판단하지 않는다 — 회원끼리 주고받은 댓글도 세기 때문이다.
     * 관리자가 확정한 답변만 '완료'다. */
    $done = sql_fetch("select qa_id from ex_qna
                        where bo_table = '$boq' and wr_id = " . (int)$r['wr_id'] . "
                          and qa_status = 'approved' limit 1");

    $items[] = array(
        'wr_id'    => (int)$r['wr_id'],
        'subject'  => $r['wr_subject'],
        'name'     => $r['wr_name'],
        'category' => $r['wr_category'],
        'replies'  => (int)$r['wr_comment'],
        'date'     => substr($r['wr_datetime'], 2, 8),      // 26-07-30
        'answered' => $done ? 1 : 0,
        'href'     => G5_BBS_URL . '/board.php?bo_table=' . rawurlencode($bo)
                    . '&wr_id=' . (int)$r['wr_id'],
    );
}

$base = G5_BBS_URL . '/board.php?bo_table=' . rawurlencode($bo);

ex_out(array(
    'ok'         => 1,
    'pd'         => $pd,
    'pd_name'    => $prod['pd_name'],
    'bo_table'   => $bo,
    'bo_subject' => $board['bo_subject'],
    'categories' => $cats,
    'sj'         => $sj,
    'category'   => $cat,
    'items'      => $items,
    'board_url'  => $base . ($cat !== '' ? '&sca=' . rawurlencode($cat) : ''),
    // 글쓰기 화면. 과목이 선택돼 있으면 말머리를 미리 채워 보낸다 —
    // 이용자가 과목을 다시 고르지 않아도 되고, 말머리 누락도 줄어든다.
    'write_url'  => G5_BBS_URL . '/write.php?bo_table=' . rawurlencode($bo)
                  . ($cat !== '' ? '&sca=' . rawurlencode($cat) : ''),
));
