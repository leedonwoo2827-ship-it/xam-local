<?php
/**
 * /exam/report.php?pd=sqld[&at=123] — 성적표(분석 리포트)
 *
 * 채점이 점수만 보여주고 끝나지 않게 하는 화면이다.
 *   점수 · 합격 판정  →  과목별 취약도  →  취약 개념  →  문항별  →  반복 오답
 *   →  다음에 볼 것(이론 · 질문)
 *
 * ── 정책: 로그인 회원 무료 ─────────────────────────────────────────────────
 * 오답노트와 같은 취급이다. 성적표는 "네가 약한 곳이 여기다" 를 보여주는 화면이고
 * 그게 곧 질문할 이유를 만든다 — 유료로 막으면 유료 전환의 입구를 잠그는 셈이 된다.
 * 비용이 드는 것(LLM 맞춤 코멘트)만 나중에 수강생으로 제한한다.
 *
 * ⚠ 비회원은 채점 기록이 남지 않는다(grade.php 가 mb_id 있을 때만 INSERT).
 *   그래서 로그인이 필요한 건 정책이 아니라 구조다.
 *
 * ⚠ LLM 을 쓰지 않는다. 전부 집계 쿼리다(api/report.php). API 비용 0.
 */
include_once('../common.php');

/* 샘플(데모) — `?sample=1` 이면 로그인 없이 열린다.
   합성 답안지라 회원 데이터를 읽지 않는다(api/lib/sample.php).
   신규 방문자·강사에게 "채점 뒤에 무엇이 나오는지" 를 보여주는 유일한 경로다. */
$sample = !empty($_GET['sample']);

if (!$is_member && !$sample) {
    goto_url(G5_BBS_URL . '/login.php?url=' . urlencode(G5_URL . '/exam/report.php'
           . (isset($_GET['pd']) ? '?pd=' . urlencode($_GET['pd']) : '')));
}

/* 문제집 — 형식 + 실재 확인. 기본값을 박지 않는다(문제집이 여러 개다). */
$pd_want = preg_match('/^[a-z0-9\-]{1,20}$/', isset($_GET['pd']) ? $_GET['pd'] : '')
         ? $_GET['pd'] : '';
$pd = '';
if ($pd_want !== '') {
    $r = sql_fetch("select pd_id from ex_product where pd_id = '" . sql_real_escape_string($pd_want) . "'");
    if ($r) $pd = $r['pd_id'];
}
$at = isset($_GET['at']) ? (int)$_GET['at'] : 0;

/* 샘플은 문제집이 정해져 있어야 한다 — 비회원이라 books[] 로 고를 수 없다.
   문제가 들어 있는 첫 문제집을 쓴다(빅분기가 먼저 열려도 코드 수정이 없다). */
if ($sample && $pd === '') {
    $r = sql_fetch("select pd_id from ex_product where pd_open = 1 order by pd_sort limit 1");
    if ($r) $pd = $r['pd_id'];
}

@include_once(G5_PATH . '/exam/brand.php');
if (!isset($EX_BRAND)) $EX_BRAND = 'XAMpass';

$g5['title'] = '성적표';
include_once(G5_PATH . '/head.php');

$rp_v = function ($f) { return @filemtime(G5_PATH . '/exam/' . $f) ?: 0; };
?>

<link rel="stylesheet" href="<?php echo G5_URL ?>/exam/assets/mypage.css?v=<?php echo $rp_v('assets/mypage.css') ?>">
<link rel="stylesheet" href="<?php echo G5_URL ?>/exam/assets/report.css?v=<?php echo $rp_v('assets/report.css') ?>">

<div class="rp" data-pd="<?php echo htmlspecialchars($pd) ?>" data-at="<?php echo (int)$at ?>"
     data-sample="<?php echo $sample ? 1 : 0 ?>"
     data-brand="<?php echo htmlspecialchars($EX_BRAND) ?>">

<?php if ($sample) { ?>
  <?php /* 샘플임을 화면에 못 박는다. 이게 없으면 자기 점수로 오해한다. */ ?>
  <div class="rp-demo">
    <b>샘플 성적표입니다.</b> 실제 응시 기록이 아니라 <?php echo htmlspecialchars($pd) ?> 문제를
    예시 답안으로 채점한 결과입니다. 내 성적표는 문제를 풀고 채점하면 만들어집니다.
    <a href="<?php echo G5_URL ?>/exam/check.php?pd=<?php echo urlencode($pd) ?>">문제 풀러 가기 →</a>
  </div>
<?php } ?>

  <div class="crumb-bar"><div class="wrap">
    <div class="crumb" id="rpCrumb">
      <a href="<?php echo G5_URL ?>/exam/"><?php echo htmlspecialchars($EX_BRAND) ?></a>
      <span class="sep">›</span><b>성적표</b>
    </div>
  </div></div>

  <div class="mp-head">
    <div>
      <h2>성적표</h2>
      <p class="mp-sub" id="rpSub">불러오는 중…</p>
    </div>
    <div class="mp-actions" id="rpActions"></div>
  </div>

  <div id="rpBody">
    <div class="mp-empty">불러오는 중…</div>
  </div>
</div>

<script src="<?php echo G5_URL ?>/exam/assets/ui.js?v=<?php echo $rp_v('assets/ui.js') ?>"></script>
<script src="<?php echo G5_URL ?>/exam/assets/report.js?v=<?php echo $rp_v('assets/report.js') ?>"></script>

<?php
include_once(G5_PATH . '/tail.php');
