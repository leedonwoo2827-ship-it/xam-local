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

/* ── 문제집 ─────────────────────────────────────────────────────────────────
 * 형식이 맞고 **ex_product 에 실재하는** 것만 통과시킨다.
 * 기본값을 'sqld' 로 두지 않는다 — 문제집이 여러 개인 지금은 그게
 * "다른 문제집을 보려는데 SQLD 가 뜨는" 경로가 된다.
 * 빈 값이면 mypage.js 가 me.php 의 books[0] 으로 정한다(수강 중인 첫 문제집).
 */
$pd_want = preg_match('/^[a-z0-9\-]{1,20}$/', isset($_GET['pd']) ? $_GET['pd'] : '')
         ? $_GET['pd'] : '';
$pd = '';
if ($pd_want !== '') {
    $r = sql_fetch("select pd_id from ex_product
                     where pd_id = '" . sql_real_escape_string($pd_want) . "'");
    if ($r) $pd = $r['pd_id'];
}

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
      <?php /* pd 가 비어 있으면(주소에 ?pd= 없음) 문제집 목록으로 보낸다.
               빈 pd 로 check.html 을 열면 어느 문제집인지 정해지지 않는다. */ ?>
      <a class="mp-btn" href="<?php echo G5_URL ?>/exam/<?php
         echo $pd !== '' ? 'check.html?pd=' . urlencode($pd) : '' ?>">문제 풀러 가기</a>
      <a class="mp-btn ghost" href="<?php echo G5_BBS_URL ?>/member_confirm.php?url=<?php echo urlencode(G5_BBS_URL.'/member_form.php') ?>">회원정보 수정</a>
    </div>
  </div>

  <?php /* 문제집 선택 — me.php 의 books[] 로 mypage.js 가 채운다.
           서버에서 그리지 않는 이유: 잔액·정산이 credit.php 를 거쳐야 하고
           그 로직을 화면과 API 두 곳에 두지 않기 위해서다. */ ?>
  <div id="mpBooks"></div>

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
