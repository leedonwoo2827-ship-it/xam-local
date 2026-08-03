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
            <?php /* $EX_* · $ex_books · $ex_pd 는 head.php 가 정의한다.
                     tail 이 head 없이 불리는 경로는 없지만(그누보드가 짝으로 include),
                     방어적으로 기본값을 둔다 — 푸터 하나 때문에 페이지가 죽으면 안 된다. */ ?>
            <h2><?php echo isset($EX_BRAND) ? htmlspecialchars($EX_BRAND) : 'XAMpass' ?></h2>
            <p class="ft_info"><?php
              echo isset($EX_INTRO)
                ? nl2br(htmlspecialchars($EX_INTRO))
                : '자격증 문제은행과 1:1 질문 서비스.' ?></p>
        </div>

        <div class="ft_cnt">
            <h2>문제집</h2>
            <?php /* 문제집 목록을 DB 에서 그린다. 'SQLD' 를 박아두면 문제집을 추가할 때마다
                     푸터를 고치게 되고, 형제 사이트로 복사하면 없는 자격증이 뜬다.
                     푸터라 5개까지만 — 그 이상은 문제집 목록으로 보낸다. */ ?>
            <?php foreach (array_slice(isset($ex_books) ? $ex_books : array(), 0, 5) as $ex_b) { ?>
              <a href="<?php echo $ex_url ?>/check.php?pd=<?php echo urlencode($ex_b['pd_id']) ?>"><?php
                echo htmlspecialchars($ex_b['pd_name']) ?></a>
            <?php } ?>
            <?php if (count(isset($ex_books) ? $ex_books : array()) > 5) { ?>
              <a href="<?php echo $ex_url ?>/">전체 보기</a>
            <?php } ?>
            <a href="<?php echo $ex_url ?>/buy.php<?php
              echo (isset($ex_pd) && $ex_pd !== '') ? '?pd=' . urlencode($ex_pd) : '' ?>">수강 신청</a>
        </div>

        <?php /* ── 주요 기능 두 칸 ──────────────────────────────────────────
           이용·고객지원 링크는 나중에 사이트맵 푸터로 내린다. 지금 이 자리는
           "무엇을 주는 제품인가" 를 말하는 데 쓴다.

           ⚠ 랜딩(scripts/landing_template.html)의 푸터와 **같은 내용이어야 한다.**
             푸터가 두 곳에 있다(정적 페이지 / PHP 화면) — 한쪽만 고치면 화면을
             옮겨 다니면서 푸터가 달라진다. 실제로 그렇게 어긋났다. */ ?>
        <div class="ft_cnt">
            <h2>주요 기능 · 수험생</h2>
            <a href="<?php echo $ex_url ?>/check.php<?php
              echo (isset($ex_pd) && $ex_pd !== '') ? '?pd=' . urlencode($ex_pd) : '' ?>">회차별 모의고사 · 즉시 채점</a>
            <a href="<?php echo $ex_url ?>/report.php?sample=1<?php
              echo (isset($ex_pd) && $ex_pd !== '') ? '&amp;pd=' . urlencode($ex_pd) : '' ?>">성적표 — 과목별 취약도·취약 개념</a>
            <a href="<?php echo $ex_url ?>/mypage.php?sample=1">오답노트 · 응시 이력 보관</a>
            <a href="<?php echo $ex_url ?>/check.php?m=theory<?php
              echo (isset($ex_pd) && $ex_pd !== '') ? '&amp;pd=' . urlencode($ex_pd) : '' ?>">과목별 이론 요약노트</a>
            <a href="<?php echo $ex_url ?>/check.php?m=board<?php
              echo (isset($ex_pd) && $ex_pd !== '') ? '&amp;pd=' . urlencode($ex_pd) : '' ?>">과목게시판 1:1 질문</a>
        </div>

        <div class="ft_cnt">
            <h2>주요 기능 · 운영·도입</h2>
            <?php /* 한 줄씩 블록으로 둔다. `<p>` + `<br>` 로 묶으면 옆의 '수험생' 열은
                     링크가 한 줄씩 떨어지는데 이 열만 문단처럼 붙어 보인다 —
                     같은 푸터 안에서 두 열의 리듬이 어긋난다.
                     `.ft_txt` 는 `#ft .ft_cnt a` 와 같은 블록·행간을 쓴다(gnuboard-skin.css).

                     ⚠ 답변 초안 일괄 생성은 아직 안 붙었다(DeepSeek 키 발급 전).
                       qa_draft 컬럼·상태·검수 화면은 준비됐지만 모델을 태우지 않는다.
                       되는 것처럼 적지 않는다 — 랜딩 푸터와 같은 기준이다. */ ?>
            <?php /* 착지점은 features.php(자료화면)다. 관리자 화면으로 직접 보내면
                     방문자가 관리자 로그인으로 튕겨 '링크가 죽었다'로 읽힌다.
                     features.php 는 관리자로 로그인했을 때만 실제 화면 링크를 덧붙인다. */ ?>
            <a href="<?php echo $ex_url ?>/features.php#review">질문 검수 큐 — 답변 전 관리자 승인</a>
            <a href="<?php echo $ex_url ?>/features.php#draft" class="ft_soon">답변 초안 일괄 생성 <em>준비 중</em></a>
            <a href="<?php echo $ex_url ?>/features.php#import">문제 일괄 등록 · 변경분만 갱신</a>
            <a href="<?php echo $ex_url ?>/features.php#quality">실 정답률로 문제 오류 자동 발견</a>
            <a href="<?php echo $ex_url ?>/features.php#credit">수강·포인트 문제집 단위 분리</a>
            <a href="<?php echo $ex_url ?>/features.php#multipd">자격증 추가 = DB 1행 (코드 변경 0)</a>
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
        <span>&copy; <?php echo date('Y') ?> <?php
          echo isset($EX_BRAND) ? htmlspecialchars($EX_BRAND) : 'XAMpass' ?></span>
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
