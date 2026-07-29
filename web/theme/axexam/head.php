<?php
if (!defined('_GNUBOARD_')) exit; // 개별 페이지 접근 불가

/**
 * theme/axexam/head.php — 문제집 포털 헤더
 *
 * theme/basic 을 통째로 복제하지 않고 **최소 파일만** 둔다.
 * skin/ · css/ · img/ 를 넣지 않으면 그누보드가 루트의 것을 그대로 쓴다
 * (theme.config.php 에서 스킨을 강제하지 않는 한). 460파일 → 5파일.
 *
 * theme/ 하위의 우리 디렉터리명은 배포본에 없으므로 그누보드 업데이트에 안전하다
 * (GNUBOARD-FACTS §11 의 공식 확장 지점).
 *
 * 모바일: theme.config.php 에서 G5_THEME_DEVICE='pc' 로 고정했다.
 * mobile/ 디렉터리를 두지 않았고(basic 의 것은 1.1MB), 우리는 반응형 한 벌로 간다.
 * 그래서 G5_IS_MOBILE 분기가 필요 없다.
 */

include_once(G5_THEME_PATH . '/head.sub.php');
include_once(G5_LIB_PATH . '/latest.lib.php');
include_once(G5_LIB_PATH . '/outlogin.lib.php');
include_once(G5_LIB_PATH . '/poll.lib.php');
include_once(G5_LIB_PATH . '/visit.lib.php');
include_once(G5_LIB_PATH . '/connect.lib.php');
include_once(G5_LIB_PATH . '/popular.lib.php');

$ex_url = G5_URL . '/exam';
?>

<!-- 상단 시작 { -->
<div id="hd">
    <h1 id="hd_h1"><?php echo $g5['title'] ?></h1>
    <div id="skip_to_container"><a href="#container">본문 바로가기</a></div>

    <?php
    if (defined('_INDEX_')) {                 // index 에서만
        include G5_BBS_PATH . '/newwin.inc.php';   // 팝업레이어
    }
    ?>

    <!-- 상단 얇은 바 —
         basic 은 여기에 '커뮤니티 / 쇼핑몰' 과 'FAQ · Q&A · 새글 · 접속자' 를 하드코딩해 둔다.
         영카트를 쓰지 않으므로 쇼핑몰을 빼고, 우리 동선으로 바꿨다. -->
    <div id="tnb">
        <div class="inner">
            <ul id="hd_define">
                <li class="active"><a href="<?php echo $ex_url ?>/">문제집</a></li>
                <li><a href="<?php echo $ex_url ?>/buy.php?pd=sqld">수강 신청</a></li>
            </ul>
            <ul id="hd_qnb">
                <li><a href="<?php echo G5_BBS_URL ?>/board.php?bo_table=notice">공지사항</a></li>
                <li><a href="<?php echo G5_BBS_URL ?>/qalist.php">1:1 문의</a></li>
                <li><a href="<?php echo G5_BBS_URL ?>/faq.php">FAQ</a></li>
            </ul>
        </div>
    </div>

    <div id="hd_wrapper">
        <div id="logo">
            <!-- 문자 워드마크(임시). 실제 로고가 나오면 이 <a> 안을 <img> 로 바꾸면 된다. -->
            <a href="<?php echo $ex_url ?>/" class="ax-word">AX<i>EXAM</i></a>
        </div>

        <div class="hd_sch_wr">
            <fieldset id="hd_sch">
                <legend>사이트 내 전체검색</legend>
                <form name="fsearchbox" method="get" action="<?php echo G5_BBS_URL ?>/search.php" onsubmit="return fsearchbox_submit(this);">
                    <input type="hidden" name="sfl" value="wr_subject||wr_content">
                    <input type="hidden" name="sop" value="and">
                    <label for="sch_stx" class="sound_only">검색어<strong class="sound_only"> 필수</strong></label>
                    <input type="text" name="stx" id="sch_stx" maxlength="20" placeholder="검색어를 입력해주세요">
                    <button type="submit" id="sch_submit" value="검색"><i class="fa fa-search" aria-hidden="true"></i><span class="sound_only">검색</span></button>
                </form>
            </fieldset>
            <script>
            function fsearchbox_submit(f){
                if (f.stx.value.length < 2) { alert("검색어는 두 글자 이상 입력하십시오."); f.stx.select(); f.stx.focus(); return false; }
                // 검색어에 아래 문자가 포함되어 있으면 검색되지 않는다
                var re = /['\"%=\*]/;
                if (re.test(f.stx.value)) { alert("특수문자는 검색할 수 없습니다."); f.stx.select(); f.stx.focus(); return false; }
                return true;
            }
            </script>
        </div>

        <ul class="hd_login">
        <?php if ($is_member) { ?>
            <li><a href="<?php echo $ex_url ?>/mypage.php">마이페이지</a></li>
            <?php if ($is_admin) { ?><li><a href="<?php echo G5_ADMIN_URL ?>/">관리자</a></li><?php } ?>
            <li><a href="<?php echo G5_BBS_URL ?>/logout.php">로그아웃</a></li>
        <?php } else { ?>
            <li><a href="<?php echo G5_BBS_URL ?>/register.php">회원가입</a></li>
            <li><a href="<?php echo G5_BBS_URL ?>/login.php">로그인</a></li>
        <?php } ?>
        </ul>
    </div>

    <?php
    /* 메뉴(#gnb) — 관리자 → 환경설정 → 메뉴설정 에서 등록한 데이터로 그린다.
     *
     * basic 테마는 메뉴가 하나도 없으면
     *   "메뉴 준비 중입니다. 관리자모드 > 환경설정 > 메뉴설정에서 설정하실 수 있습니다."
     * 를 **이용자에게 그대로** 보여준다. 그건 운영자에게 할 말이지 방문자에게 할 말이 아니다.
     * → 비어 있으면 영역을 통째로 생략한다. 등록하면 자동으로 다시 나온다.
     */
    $ex_menus = get_menu_db(0, true);
    $ex_has_menu = false;
    foreach ((array)$ex_menus as $ex_r) { if (!empty($ex_r)) { $ex_has_menu = true; break; } }

    if ($ex_has_menu) {
    ?>
    <nav id="gnb">
        <h2>메인메뉴</h2>
        <div class="gnb_wrap">
            <ul id="gnb_1dul">
            <?php
            $gnb_z = 999;
            foreach ($ex_menus as $row) {
                if (empty($row)) continue;
                $add_class = (isset($row['sub']) && $row['sub']) ? 'gnb_al_li_plus' : '';
            ?>
                <li class="gnb_1dli <?php echo $add_class ?>" style="z-index:<?php echo $gnb_z-- ?>">
                    <a href="<?php echo $row['me_link'] ?>" target="_<?php echo $row['me_target'] ?>" class="gnb_1da"><?php echo $row['me_name'] ?></a>
                    <?php
                    $k = 0;
                    foreach ((array)$row['sub'] as $row2) {
                        if (empty($row2)) continue;
                        if ($k == 0) echo '<span class="bg">하위분류</span><div class="gnb_2dul"><ul class="gnb_2dul_box">';
                    ?>
                        <li class="gnb_2dli"><a href="<?php echo $row2['me_link'] ?>" target="_<?php echo $row2['me_target'] ?>" class="gnb_2da"><?php echo $row2['me_name'] ?></a></li>
                    <?php
                        $k++;
                    }
                    if ($k > 0) echo '</ul></div>';
                    ?>
                </li>
            <?php } ?>
            </ul>
        </div>
    </nav>
    <?php } ?>
</div>
<!-- } 상단 끝 -->

<!-- 콘텐츠 시작 { -->
<div id="wrapper">
    <div id="container_wr">
    <div id="container">
        <?php if (!defined('_INDEX_')) { ?>
        <h2 id="container_title"><span title="<?php echo get_text($g5['title']) ?>"><?php echo get_head_title($g5['title']) ?></span></h2>
        <?php } ?>
