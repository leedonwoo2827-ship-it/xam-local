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

/* ── 브랜드 ─────────────────────────────────────────────────────────────────
 * 06/brand.php 는 build_check.py 가 data/brand.json 에서 생성해 06/ 업로드에 실려 온다.
 * @include_once 로 부르고 인라인 기본값을 남겨두는 이유: 테마만 올리고 06/ 을 아직
 * 안 올린 상태에서도 화면이 떠야 한다. 없으면 로고가 빈 채로 배포된다.
 */
@include_once(G5_PATH . '/exam/brand.php');
if (!isset($EX_BRAND))      $EX_BRAND      = 'XAMpass';
if (!isset($EX_BRAND_HTML)) $EX_BRAND_HTML = '<i>XAM</i>pass';
if (!isset($EX_TAGLINE))    $EX_TAGLINE    = '자격증 문제은행';
if (!isset($EX_INTRO))      $EX_INTRO      = '자격증 문제은행과 1:1 질문 서비스.';

/* ── 문제집 목록 ────────────────────────────────────────────────────────────
 * nav 의 '문제 풀기'·'이론'·'수강 신청' 이 어느 문제집을 가리킬지 DB 에서 정한다.
 * pd=sqld 를 박아두면 문제집을 추가할 때마다 이 파일을 고치게 되고,
 * 형제 사이트로 복사하면 존재하지 않는 자격증으로 링크가 간다.
 *
 * 노출 중이고 **문제가 실제로 있는** 것만. 문제 0건인 품목으로 보내면 빈 화면이 뜬다
 * (api/products.php:40 과 같은 판정이다).
 *
 * 쿼리 1회이고 품목은 많아도 수십 행이라 매 페이지 부담이 없다.
 */
$ex_books = array();
$ex_res = sql_query("select d.pd_id, d.pd_name
                       from ex_product d
                      where d.pd_open = 1
                        and exists (select 1 from ex_problem x
                                     where x.pd_id = d.pd_id and x.pr_open = 1)
                      order by d.pd_sort, d.pd_id", false);
while ($ex_res && $ex_r = sql_fetch_array($ex_res)) $ex_books[] = $ex_r;

// nav 가 가리킬 기본 문제집. 하나도 없으면(문제 임포트 전) 링크를 문제집 목록으로 보낸다.
$ex_pd = $ex_books ? $ex_books[0]['pd_id'] : '';
?>

<!-- 상단 시작 { -->
<div id="hd">
    <h1 id="hd_h1" class="sound_only"><?php echo $g5['title'] ?></h1>
    <div id="skip_to_container"><a href="#container">본문 바로가기</a></div>

    <?php
    if (defined('_INDEX_')) {                 // index 에서만
        include G5_BBS_PATH . '/newwin.inc.php';   // 팝업레이어
    }

    /* ═══ 공용 네비 ═══════════════════════════════════════════════════
     * ⚠ /exam/index.html · /exam/check.html 과 **같은 마크업**을 유지한다.
     *   한쪽만 고치면 화면마다 헤더가 달라진다. CSS 는 /exam/assets/axnav.css 하나를
     *   세 곳이 공유하고, extend/10_exam.php 가 그누보드 쪽에 주입한다.
     *
     * 아이콘: ui.js 의 스프라이트(#i-*)를 쓴다. 그누보드 화면에는 ui.js 가 없으므로
     *   여기서만 로드한다 — 48개 아이콘 + 차트, 10KB.
     */
    $ex_here = $_SERVER['REQUEST_URI'];
    $on = function ($frag) use ($ex_here) {
        return (strpos($ex_here, $frag) !== false) ? ' on' : '';
    };
    ?>
    <script src="<?php echo $ex_url ?>/assets/ui.js"></script>

    <header class="axnav">
      <div class="axnav-in">
        <a class="axnav-logo" href="<?php echo $ex_url ?>/"><?php echo $EX_BRAND_HTML ?></a>
        <nav class="axnav-main">
          <?php
          /* pd 를 붙인 링크. 문제집이 하나도 없으면 목록으로 보낸다 —
             빈 pd 로 check.php 를 열면 어느 문제집인지 정해지지 않는다. */
          $ex_q  = $ex_pd !== '' ? '?pd=' . urlencode($ex_pd) : '';
          $ex_go = function ($page, $extra = '') use ($ex_url, $ex_pd, $ex_q) {
              if ($ex_pd === '') return $ex_url . '/';
              return $ex_url . '/' . $page . $ex_q . $extra;
          };
          ?>
          <?php
          /* ★ 내비는 **문제집 이름**을 직접 띄운다.
           *
           *   예전에는 `문제집` · `문제 풀기` · `이론` 세 개였다. 기능 이름이라 어느
           *   자격증인지 알 수 없고, `문제 풀기` 는 $ex_books[0](정렬 첫 품목) 하나로만
           *   갔다. 품목이 둘이 되자 "다른 자격증은 어디로 들어가나" 가 됐다.
           *
           *   → 문제집을 이름으로 나열한다. 누르면 그 문제집 문제풀이로 간다.
           *     목록은 위에서 DB 로 뽑은 $ex_books 라 품목이 늘어도 이 파일을 안 고친다.
           *     이론은 그 화면 안의 탭(&m=theory)이므로 내비에서 뺀다 — 문제집을 고르기
           *     전에는 어느 이론인지 정할 수 없다.
           */
          foreach ($ex_books as $ex_b) {
              $bid  = $ex_b['pd_id'];
              $bq   = '?pd=' . urlencode($bid);
              $bon  = (strpos($_SERVER['REQUEST_URI'], 'pd=' . $bid) !== false
                       && strpos($_SERVER['REQUEST_URI'], 'check.php') !== false) ? ' on' : '';
              echo '<a class="axnav-item' . $bon . '" href="' . $ex_url . '/check.php' . $bq . '">'
                 . '<svg class="ic"><use href="#i-edit"></use></svg>'
                 . htmlspecialchars($ex_b['pd_name']) . '</a>';
          }
          if (!$ex_books) {
              // 문제 임포트 전 — 링크할 곳이 없다. 목록으로 보낸다.
              echo '<a class="axnav-item" href="' . $ex_url . '/">'
                 . '<svg class="ic"><use href="#i-clipboard"></use></svg>문제집</a>';
          }
          ?>
          <a class="axnav-item<?php echo $on('buy.php') ?>" href="<?php echo $ex_go('buy.php') ?>"><svg class="ic"><use href="#i-cap"></use></svg>수강 신청</a>
          <?php /* 성적표 샘플 — 로그인·응시 없이 열린다(api/lib/sample.php).
                   채점 뒤에 무엇이 나오는지 보여주는 유일한 경로다. */ ?>
          <a class="axnav-item<?php echo $on('sample=1') ?>" href="<?php echo $ex_go('report.php', '&amp;sample=1') ?>"><svg class="ic"><use href="#i-chart"></use></svg>성적표 샘플</a>
        </nav>
        <nav class="axnav-util">
          <a class="axnav-item<?php echo $on('bo_table=notice') ?>" href="<?php echo G5_BBS_URL ?>/board.php?bo_table=notice"><svg class="ic"><use href="#i-bell"></use></svg>공지</a>
          <a class="axnav-item<?php echo $on('qalist') ?>" href="<?php echo G5_BBS_URL ?>/qalist.php"><svg class="ic"><use href="#i-help"></use></svg>문의</a>
          <span class="axnav-sep"></span>
        <?php if ($is_member) { ?>
          <span class="axnav-me"><b><?php echo htmlspecialchars($member['mb_nick'] ?: $member['mb_id']) ?></b>님</span>
          <a class="axnav-item" href="<?php echo $ex_url ?>/mypage.php"><svg class="ic"><use href="#i-user"></use></svg>마이페이지</a>
          <?php if ($is_admin) { ?>
          <a class="axnav-item" href="<?php echo G5_ADMIN_URL ?>/"><svg class="ic"><use href="#i-shield"></use></svg>관리자</a>
          <?php } ?>
          <?php /* 로그아웃 후 갈 곳을 명시한다. 지정하지 않으면 G5_URL(루트)로 가는데
                   루트가 /exam/ 으로 리다이렉트돼서 '메인으로 튕겼다'로 읽힌다.
                   ⚠ url 에 도메인을 넣으면 logout.php 가 거부한다 — 경로만 준다. */ ?>
          <a class="axnav-cta" href="<?php echo G5_BBS_URL ?>/logout.php?url=<?php echo urlencode('/exam/') ?>">로그아웃</a>
        <?php } else { ?>
          <?php /* 회원가입도 버튼이다 — 정적 페이지(index.html·detail.html)의 헤더와
                   같은 모양이어야 한다. 화면을 옮겨 다니면서 버튼이 텍스트로 바뀌면
                   같은 헤더로 읽히지 않는다. 채워진 버튼은 '로그인' 하나로 유지한다. */ ?>
          <a class="axnav-cta ghost<?php echo $on('register') ?>" href="<?php echo G5_BBS_URL ?>/register.php">회원가입</a>
          <a class="axnav-cta" href="<?php echo G5_BBS_URL ?>/login.php">로그인</a>
        <?php } ?>
        </nav>
      </div>
    </header>

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
