<?php
/**
 * /exam/mypage.php — 마이페이지
 *
 * 그누보드 테마(axexam)의 head/tail 을 그대로 쓴다 → 헤더·푸터가 전 화면과 통일된다.
 * 데이터는 클라이언트에서 우리 API 로 받는다(me / attempts / wrong / qna).
 * 그래야 이 파일이 화면만 담당하고 로직이 한 군데(API)에 모인다.
 *
 * ⚠ 잔여 질문권은 지금 항상 0 이다 — 크레딧(S6)을 아직 붙이지 않았다.
 *   화면에서 그 사실을 숨기지 않고 "무료 기간" 으로 표시한다.
 */
include_once('../common.php');

if (!$is_member) {
    goto_url(G5_BBS_URL . '/login.php?url=' . urlencode(G5_URL . '/exam/mypage.php'));
}

$pd = preg_match('/^[a-z0-9\-]{1,20}$/', isset($_GET['pd']) ? $_GET['pd'] : '')
    ? $_GET['pd'] : 'sqld';

$g5['title'] = '마이페이지';
include_once(G5_PATH . '/head.php');
?>

<link rel="stylesheet" href="<?php echo G5_URL ?>/exam/assets/mypage.css?v=<?php echo @filemtime(G5_PATH.'/exam/assets/mypage.css') ?>">

<div class="mp" data-pd="<?php echo htmlspecialchars($pd) ?>">

  <div class="mp-head">
    <div>
      <h2><?php echo htmlspecialchars($member['mb_nick'] ?: $member['mb_id']) ?>님</h2>
      <p class="mp-sub">가입 <?php echo substr($member['mb_datetime'], 0, 10) ?></p>
    </div>
    <div class="mp-actions">
      <a class="mp-btn" href="<?php echo G5_URL ?>/exam/check.html?pd=<?php echo urlencode($pd) ?>">문제 풀러 가기</a>
      <a class="mp-btn ghost" href="<?php echo G5_BBS_URL ?>/member_confirm.php?url=<?php echo urlencode(G5_BBS_URL.'/member_form.php') ?>">회원정보 수정</a>
    </div>
  </div>

  <!-- 요약 4칸 -->
  <div class="mp-stats" id="mpStats">
    <div class="mp-stat"><div class="n">–</div><div class="l">응시 횟수</div></div>
    <div class="mp-stat"><div class="n">–</div><div class="l">평균 점수</div></div>
    <div class="mp-stat"><div class="n">–</div><div class="l">오답 문제</div></div>
    <div class="mp-stat"><div class="n">–</div><div class="l">남은 질문</div></div>
  </div>

  <div class="mp-tabs" id="mpTabs">
    <button class="on" data-t="attempt">응시 이력</button>
    <button data-t="wrong">오답노트</button>
    <button data-t="qna">내 질문</button>
  </div>

  <div class="mp-panel" id="mpPanel">
    <div class="mp-empty">불러오는 중…</div>
  </div>
</div>

<script src="<?php echo G5_URL ?>/exam/assets/mypage.js?v=<?php echo @filemtime(G5_PATH.'/exam/assets/mypage.js') ?>"></script>

<?php
include_once(G5_PATH . '/tail.php');
