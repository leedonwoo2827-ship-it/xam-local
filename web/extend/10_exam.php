<?php
if (!defined('_GNUBOARD_')) exit;

/**
 * extend/10_exam.php — 문제집 앱 배선
 *
 * 근거: common.php L836~853 이 extend/ 의 `.php` 를 natsort 순서로 include 한다.
 *       주석에 "common.php 파일을 수정할 필요가 없도록 확장합니다" 라고 적혀 있는
 *       그누보드5의 공식 확장 지점이다. 파일명 앞의 숫자로 로드 순서를 잡는다.
 *
 * ⚠ 이 파일은 **모든 그누보드 페이지에서** 실행된다.
 *   무거운 로직을 여기 넣지 않는다. 지금은 상수 등록과 CSS 한 줄뿐이다.
 */

/* ── 커스텀 테이블명 ───────────────────────────────────────────────────
 * `ex_` 무접두를 쓴다. G5_TABLE_PREFIX(g5_) 를 붙이지 않는다 —
 * 우리 테이블은 그누보드 테이블이 아니므로 네임스페이스를 섞지 않는다.
 * (extend/social_login.extend.php 가 $g5[...] 에 테이블명을 넣는 선례를 따르되
 *  접두어만 우리 것으로 한다. 실제 쿼리는 리터럴을 쓰고 이건 참조용이다.) */
$g5['exam_product_table'] = 'ex_product';
$g5['exam_problem_table'] = 'ex_problem';
$g5['exam_qna_table']     = 'ex_qna';
$g5['exam_credit_table']  = 'ex_credit_lot';
$g5['exam_order_table']   = 'ex_order';

define('G5_EXAM_URL',  G5_URL . '/exam');
define('G5_EXAM_PATH', G5_PATH . '/exam');

/* ── 그누보드 화면에 우리 팔레트를 씌운다 ──────────────────────────────
 *
 * 왜 CSS 만 얹는가:
 *   로그인·회원가입·비밀번호찾기는 **법적 문구·검증·메일 흐름이 완성품**이다.
 *   마크업을 다시 짜면 소셜로그인 배선(plugin/social)과 약관 동의 흐름이 깨진다.
 *   그래서 skin/member/basic 과 theme/basic 은 그대로 두고 색만 덮는다.
 *
 * 왜 add_stylesheet() 인가:
 *   <link> 를 직접 박으면 그누보드의 출력 버퍼 후처리
 *   (html_process_css_files replace 훅)와 위치가 어긋날 수 있다.
 *   두 번째 인자가 출력 순서이고, 큰 값이라야 theme/basic 뒤에 와서 이긴다.
 *
 * ⚠ 코어 파일을 하나도 고치지 않는다. 이 파일과 /exam/assets/ 만 우리 것이다.
 */
if (function_exists('add_stylesheet')) {
    $__ex_css = G5_PATH . '/exam/assets/gnuboard-skin.css';
    $__ex_ver = @filemtime($__ex_css);          // 캐시 무효화 — 없으면 0
    add_stylesheet(
        '<link rel="stylesheet" href="' . G5_EXAM_URL . '/assets/gnuboard-skin.css?v='
        . (int)$__ex_ver . '">',
        100
    );
    unset($__ex_css, $__ex_ver);
}
