<?php
if (!defined('_GNUBOARD_')) exit; // 개별 페이지 접근 불가

/**
 * theme/axexam/tail.php — 문제집 포털 푸터
 *
 * basic 대비 바꾼 것:
 *   · 더미 회사정보(회사명/대표자명/OO도 OO시/123-45-67890)를 뺐다.
 *     실제 사업자 정보가 아니라 **표시하면 안 되는 값**이다 —
 *     전자상거래법상 사업자 정보는 사실이어야 하고, 거짓 표기는 없느니만 못하다.
 *     ⚠ 사업자등록·통신판매업 신고가 끝나면 아래 '사업자 정보' 블록의 주석을 풀고
 *       실제 값을 넣는다. 그때는 **표시가 법적 의무**다.
 *   · 접속자집계·설문조사 위젯 제거 (이용자에게 의미 없다)
 *   · 링크를 랜딩 푸터와 같은 구성으로
 */

/* 모바일 분기 없음 — theme.config.php 의 G5_THEME_DEVICE='pc' 로 고정했다. */

$ex_url = G5_URL . '/exam';
?>

    </div>

    <?php /* 사이드 로그인 위젯은 비로그인일 때만 의미가 있다 */ ?>
    <?php if (!$is_member) { ?>
    <div id="aside">
        <?php echo outlogin('theme/basic'); ?>
    </div>
    <?php } ?>
</div>

</div>
<!-- } 콘텐츠 끝 -->

<!-- 하단 시작 { -->
<div id="ft">
    <div id="ft_wr">
        <div class="ft_cnt">
            <h2>AXEXAM</h2>
            <p class="ft_info">IT 자격증 문제은행과 1:1 질문 서비스.<br>문제·정답·해설을 전면 공개합니다.</p>
        </div>

        <div class="ft_cnt">
            <h2>문제집</h2>
            <a href="<?php echo $ex_url ?>/check.html?pd=sqld">SQLD</a>
            <a href="<?php echo $ex_url ?>/buy.php?pd=sqld">수강 신청</a>
        </div>

        <div class="ft_cnt">
            <h2>이용</h2>
            <?php if ($is_member) { ?>
                <a href="<?php echo $ex_url ?>/mypage.php">마이페이지</a>
                <a href="<?php echo G5_BBS_URL ?>/logout.php">로그아웃</a>
            <?php } else { ?>
                <a href="<?php echo G5_BBS_URL ?>/login.php">로그인</a>
                <a href="<?php echo G5_BBS_URL ?>/register.php">회원가입</a>
            <?php } ?>
        </div>

        <div class="ft_cnt">
            <h2>고객지원</h2>
            <a href="<?php echo G5_BBS_URL ?>/board.php?bo_table=notice">공지사항</a>
            <a href="<?php echo G5_BBS_URL ?>/qalist.php">1:1 문의</a>
            <a href="<?php echo G5_BBS_URL ?>/faq.php">자주 묻는 질문</a>
        </div>

        <?php /* ── 사업자 정보 ────────────────────────────────────────────
           사업자등록·통신판매업 신고가 끝나면 아래 주석을 풀고 실제 값을 넣는다.
           전자상거래법상 표시 의무 항목이다. 그 전까지는 아예 두지 않는다 —
           더미 값을 노출하는 것보다 없는 편이 낫다.

        <div class="ft_cnt">
            <h2>사업자 정보</h2>
            <p class="ft_info">
                상호 : ○○○ / 대표 : ○○○<br>
                주소 : ○○○<br>
                사업자등록번호 : ○○○-○○-○○○○○<br>
                통신판매업신고 : 제○○○호<br>
                개인정보관리책임자 : ○○○<br>
                전화 : ○○-○○○○-○○○○
            </p>
        </div>
        ─────────────────────────────────────────────────────────── */ ?>
    </div>

    <div id="ft_copy">
        <a href="<?php echo get_pretty_url('content', 'provision') ?>">이용약관</a>
        <a href="<?php echo get_pretty_url('content', 'privacy') ?>">개인정보처리방침</a>
        <span>&copy; <?php echo date('Y') ?> AXEXAM</span>
    </div>

    <button type="button" id="top_btn">
        <i class="fa fa-arrow-up" aria-hidden="true"></i><span class="sound_only">상단으로</span>
    </button>
    <script>
    $(function(){ $("#top_btn").on("click", function(){ $("html, body").animate({scrollTop:0}, 500); return false; }); });
    </script>
</div>

<?php
if ($config['cf_analytics']) echo $config['cf_analytics'];
?>
<!-- } 하단 끝 -->

<script>
$(function(){ font_resize("container", get_cookie("ck_font_resize_rmv_class"), get_cookie("ck_font_resize_add_class")); });
</script>

<?php
include_once(G5_THEME_PATH . "/tail.sub.php");
