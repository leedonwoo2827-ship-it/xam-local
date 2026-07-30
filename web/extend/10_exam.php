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
 *
 * ★★ 관리자(/adm/)에는 프론트 스킨을 주입하지 않는다 ★★
 *   gnuboard-skin.css 는 theme/basic 의 `#hd`·`#tnb`·`#gnb`·`#logo` 를 겨냥해 쓴 것인데,
 *   **그누보드 관리자의 좌측 사이드바도 `#gnb` 를 쓴다**(adm/admin.lib.php 가 그리는
 *   `#gnb > .gnb_1dli > .gnb_2dul`). 그래서 아래 두 줄이 관리자 2차 메뉴를 통째로 지웠다:
 *
 *       #gnb a{ color:#d3dcf0 !important; }     ← 흰 배경 위의 거의 흰 글자
 *       #gnb a:hover{ color:#fff !important; }  ← 호버하면 완전히 사라짐
 *
 *   `#hd`·`#tnb` 를 네이비로 덮고 `#logo a::after{content:"AXEXAM"}` 를 넣은 것도 같이 새어
 *   관리자 상단이 엉켰다. 관리자는 코어 화면 그대로 두는 것이 맞다 — 우리가 꾸밀 대상이 아니다.
 *
 *   G5_ADMIN_DIR 로 판별하는 이유: 보안상 adm 을 다른 이름으로 바꿔 쓰는 설치가 있고,
 *   그누보드가 그 값을 상수로 갖고 있다. 하드코딩된 '/adm/' 은 그 경우 빗나간다.
 *
 *   ⚠ G5_IS_ADMIN 같은 상수로는 판별할 수 없다. adm/_common.php 가 ../common.php 를
 *     **먼저** include 하므로, 이 파일이 실행되는 시점엔 아직 정의되지 않았다.
 */
if (function_exists('add_stylesheet')) {
    $__admdir = defined('G5_ADMIN_DIR') ? G5_ADMIN_DIR : 'adm';
    // SCRIPT_NAME 은 실행 중인 스크립트 경로다(REQUEST_URI 와 달리 쿼리스트링·리라이트에 흔들리지 않는다)
    $__in_adm = (strpos((string)$_SERVER['SCRIPT_NAME'], '/' . $__admdir . '/') !== false);

    // Pretendard — /exam/ 화면과 같은 얼굴을 그누보드 화면에도 준다.
    // 폰트는 관리자에서도 무해하고 오히려 읽기 좋으므로 여기서는 제외하지 않는다.
    add_stylesheet('<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>', 98);
    add_stylesheet('<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/'
                 . 'pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css">', 99);

    // 공용 네비 + 그누보드 스킨. 세 화면(랜딩·문제풀이·그누보드)이 axnav.css 를 공유한다.
    if (!$__in_adm) {
        foreach (array('axnav.css', 'gnuboard-skin.css') as $__f) {
            $__v = @filemtime(G5_PATH . '/exam/assets/' . $__f);   // 캐시 무효화 — 없으면 0
            add_stylesheet('<link rel="stylesheet" href="' . G5_EXAM_URL . '/assets/'
                         . $__f . '?v=' . (int)$__v . '">', 100);
        }
        unset($__f, $__v);
    }
    unset($__admdir, $__in_adm);
}
