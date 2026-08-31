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
 * nav 의 '문제집'·'수강 신청' 이 어느 문제집을 가리킬지 DB 에서 정한다.
 * pd=sqld 를 박아두면 문제집을 추가할 때마다 이 파일을 고치게 되고,
 * 형제 사이트로 복사하면 존재하지 않는 자격증으로 링크가 간다.
 *
 * ★ 예전에는 `exists (select 1 from ex_problem …)` 로 **문제가 있는 것만** 뽑았다.
 *   그래서 아직 문항을 안 넣은 품목이 상단 메뉴에서 통째로 사라졌다 — 라인업을
 *   18개 등록해도 메뉴에는 1~2개만 보였다. `api/products.php:26-39` 는 같은 상황을
 *   이미 다르게 처리한다(둘을 구분한다):
 *
 *     pd_open = 0            관리자가 감췄다 → 목록에 없다
 *     pd_open = 1 · 문항 0   열어뒀지만 비었다 → **'준비중' 으로 보여준다**
 *
 *   랜딩과 상단 메뉴가 서로 다른 라인업을 보여주면 안 되므로 그 판정을 여기로 옮겼다.
 *   문항 0 인 품목은 **링크를 걸지 않는다**(누르면 빈 화면이 뜬다).
 *
 * 쿼리 1회이고 품목은 많아도 수십 행이라 매 페이지 부담이 없다.
 */
$ex_books = array();
$ex_res = sql_query("select d.pd_id, d.pd_name, d.pd_config,
                            (select count(*) from ex_problem x
                              where x.pd_id = d.pd_id and x.pr_open = 1) as n_prob
                       from ex_product d
                      where d.pd_open = 1
                      order by d.pd_sort, d.pd_id", false);
while ($ex_res && $ex_r = sql_fetch_array($ex_res)) $ex_books[] = $ex_r;

/* nav 가 가리킬 기본 문제집.
 *
 * ★ `$ex_books[0]` 을 쓰면 안 된다. 위에서 준비중 품목까지 뽑으므로 정렬 첫 행이
 *   문항 0 인 품목일 수 있고, 그러면 '수강 신청'·'성적표 샘플' 이 **빈 문제집**으로 간다.
 *   문항이 실제로 있는 첫 품목을 따로 고른다. 하나도 없으면(임포트 전) 목록으로 보낸다.
 */
$ex_pd = '';
foreach ($ex_books as $ex_b) {
    if ((int)$ex_b['n_prob'] > 0) { $ex_pd = $ex_b['pd_id']; break; }
}

/* 주관처별 묶음. 키를 `정렬번호|이름` 으로 두고 ksort 하면 group_sort 순 →
 * 같은 번호면 이름 순이 되고, 열 안에서는 pd_sort(위 쿼리 순서)가 그대로 유지된다.
 *
 * 그룹은 `pd_config` 의 {"group":"…","group_sort":n} 에서 읽는다 — 이 파일에 표를
 * 만들지 않는다(products.php:14-20 과 같은 이유). 빠뜨린 품목은 '기타'(99)로 가서
 * 맨 뒤 열에 모인다 — 조용히 사라지지 않는다.
 */
$ex_groups = array();
foreach ($ex_books as $ex_b) {
    $ex_cfg = json_decode((string)$ex_b['pd_config'], true);
    if (!is_array($ex_cfg)) $ex_cfg = array();
    $ex_g  = !empty($ex_cfg['group']) ? (string)$ex_cfg['group'] : '기타';
    $ex_gs = isset($ex_cfg['group_sort']) ? (int)$ex_cfg['group_sort'] : 99;
    $ex_groups[sprintf('%03d|%s', $ex_gs, $ex_g)][] = $ex_b;
}
ksort($ex_groups);
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
          /* ★ 내비는 **문제집을 주관처별 열로 펼친다.**
           *
           *   1세대: `문제집` · `문제 풀기` · `이론` 세 개. 기능 이름이라 어느 자격증인지
           *          알 수 없고 `문제 풀기` 는 정렬 첫 품목 하나로만 갔다.
           *   2세대: 문제집 이름을 **평평하게 나열**. 둘일 때는 좋았지만 라인업이 18개가
           *          되면서 내비 한 줄을 넘겨 터졌다.
           *   3세대(지금): `문제집` 하나에 메가 드롭다운. 주관처가 열이 된다.
           *
           *   열 목록은 위에서 DB 로 묶은 $ex_groups 라 **품목이 늘어도 이 파일을 안 고친다.**
           *   이론은 그 화면 안의 탭(&m=theory)이므로 내비에서 뺀다 — 문제집을 고르기
           *   전에는 어느 이론인지 정할 수 없다.
           *
           * ⚠ 이 마크업은 `scripts/landing_template.html`·`detail_template.html` 의
           *   `fillNav()` 가 **클래스와 순서까지 똑같이** 만든다. 한쪽만 고치면 화면을
           *   옮겨 다닐 때 헤더가 달라진다(axnav.css 머리 주석의 규약).
           *
           * ★ 여는 것은 **CSS 가 한다** — `:hover` 와 `:focus-within` 이다. JS 를 쓰면
           *   정적 페이지와 그누보드에 같은 스크립트를 두 벌 둬야 하고, 그 두 벌이 갈린다.
           *   button 을 쓰는 이유는 hover 가 없는 터치·키보드에서 focus 로 열리게 하려는
           *   것이다(div 는 focus 를 못 받는다).
           */
          $ex_here_pd = (strpos($_SERVER['REQUEST_URI'], 'check.php') !== false);
          ?>
          <div class="axnav-drop">
            <button class="axnav-item axnav-drop-btn" type="button" aria-haspopup="true" aria-expanded="false">
              <svg class="ic"><use href="#i-clipboard"></use></svg>문제집<i class="axnav-caret"></i>
            </button>
            <div class="axnav-mega">
              <div class="axnav-mega-in">
                <?php foreach ($ex_groups as $ex_key => $ex_list) {
                    list(, $ex_gname) = explode('|', $ex_key, 2); ?>
                <div class="axnav-col">
                  <div class="axnav-col-h"><?php echo htmlspecialchars($ex_gname) ?></div>
                  <?php foreach ($ex_list as $ex_b) {
                      $bid  = $ex_b['pd_id'];
                      $bnm  = htmlspecialchars($ex_b['pd_name']);
                      if ((int)$ex_b['n_prob'] < 1) {
                          /* 준비중 — 링크를 걸지 않는다. 누르면 빈 화면이 뜬다. */
                          echo '<span class="axnav-sub-item is-soon">' . $bnm
                             . '<em>준비중</em></span>';
                          continue;
                      }
                      $bon = ($ex_here_pd && strpos($_SERVER['REQUEST_URI'], 'pd=' . $bid) !== false)
                             ? ' on' : '';
                      echo '<a class="axnav-sub-item' . $bon . '" href="' . $ex_url
                         . '/check.php?pd=' . urlencode($bid) . '">' . $bnm . '</a>';
                  } ?>
                </div>
                <?php } ?>
                <?php if (!$ex_books) { ?>
                <div class="axnav-col">
                  <div class="axnav-col-h">문제집</div>
                  <span class="axnav-sub-item is-soon">준비중<em>준비중</em></span>
                </div>
                <?php } ?>
              </div>
            </div>
          </div>
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
<?php
/* $ex_bare — '테마 카드를 벗는다' 는 표시다. head.php 를 include 하기 **전에**
 * 화면 쪽에서 켠다(현재 /exam/check.php 하나).
 *
 * 왜 필요한가: 문제풀이 화면은 정적 페이지에서 옮겨온 것이라 자기 배경(.page)과
 * 자기 폭 상자(.wrap)를 이미 갖고 있다. 그 위에 #container 의 흰 카드를 한 겹 더
 * 씌우면 흰 카드 안에 흰 문제 카드가 들어가고, 무엇보다 **폭을 문제가 아니라
 * 테마가 정한다** — 탭 줄에서 가장 긴 '과목게시판' 이 폭을 끌어간다.
 *
 * ⚠ 아무 화면에나 켜지 말 것. mypage.css 머리 주석에 적혀 있듯 .mp·.apply 는
 *   "#container 하위에 들어간다" 는 전제로 짜여 있어 카드의 패딩에 기대고 있다.
 *   자기 폭 상자를 가진 화면만 켠다.
 */
$ex_bare_cls = !empty($ex_bare) ? ' class="ex-bare"' : '';
?>
<div id="wrapper">
    <div id="container_wr"<?php echo !empty($ex_bare) ? ' class="ex-bare-wr"' : '' ?>>
    <div id="container"<?php echo $ex_bare_cls ?>>
        <?php /* 카드를 벗는 화면은 제목을 자기가 그린다(.head-block > h1).
                 여기서도 그리면 '…문제집' 과 '회차별 모의고사' 가 겹쳐 두 줄이 된다. */ ?>
        <?php if (!defined('_INDEX_') && empty($ex_bare)) { ?>
        <h2 id="container_title"><span title="<?php echo get_text($g5['title']) ?>"><?php echo get_head_title($g5['title']) ?></span></h2>
        <?php } ?>
