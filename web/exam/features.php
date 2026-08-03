<?php
/**
 * /exam/features.php — 기능 소개(자료화면). 푸터 '주요 기능 · 운영·도입' 의 착지점.
 *
 * ── 왜 관리자 화면으로 직접 링크하지 않는가 ────────────────────────────────
 * 자랑하려는 것은 `/adm/exam_qna_list.php` 같은 **운영 화면**인데, 방문자가 그걸
 * 누르면 관리자 로그인으로 튕긴다. "링크가 죽었다"로 읽히고, 관리자 경로만 알려주는
 * 셈이 된다. 그래서 **캡처와 설명이 있는 공개 페이지**를 착지점으로 둔다.
 *
 * 관리자로 로그인한 상태에서는 각 항목에 **실제 화면으로 가는 링크**가 함께 붙는다.
 * 같은 페이지가 방문자에게는 자료화면, 운영자에게는 이동 경로가 된다.
 *
 * ── 캡처 넣는 방법 ─────────────────────────────────────────────────────────
 * `/exam/assets/shots/<파일명>.png` 로 올리면 그 자리에 그려진다.
 * 아직 없으면 **무엇을 찍어야 하는지 점선 자리표시가 알려준다** — 빈 화면이 되지 않고,
 * 캡처가 밀렸다는 사실이 눈에 보인다(문서에 적어두면 잊는다).
 *
 * ⚠ 준비되지 않은 기능은 `'ready' => false` 로 둔다. 되는 것처럼 적지 않는다 —
 *   BACKLOG.md 에 스스로 정해둔 기준이다.
 */
include_once('../common.php');

@include_once(G5_PATH . '/exam/brand.php');
if (!isset($EX_BRAND)) $EX_BRAND = 'XAMpass';

$g5['title'] = '기능 소개';
include_once(G5_PATH . '/head.php');

$fv = function ($f) { return @filemtime(G5_PATH . '/exam/' . $f) ?: 0; };

/* 문제집 하나 — '문제 풀러 가기' 링크에 쓴다. 없으면 목록으로 보낸다. */
$r = sql_fetch("select pd_id from ex_product where pd_open = 1 order by pd_sort limit 1");
$pd1 = $r ? $r['pd_id'] : '';

/* ── 항목 정의 ──────────────────────────────────────────────────────────────
 * `shot`  : /exam/assets/shots/<shot>.png
 * `adm`   : 관리자에게만 보이는 실제 화면 경로 ('' 이면 없음)
 * `ready` : false 면 '준비 중' 배지. 링크·캡처 자리를 만들지 않는다.
 */
$FEAT = array(
  array(
    'id' => 'review', 'ready' => true,
    'h'  => '질문 검수 큐 — 답변 전 관리자 승인',
    'p'  => '회원 질문이 큐에 쌓이고, 관리자가 승인한 것만 공개된다. 검수 대기가 맨 위,'
          . ' 그다음 오래 기다린 순이다 — 오래 기다린 사람이 먼저 답을 받아야 한다.',
    'why'=> 'LLM 초안과 확정 답변을 <b>다른 컬럼</b>(<code>qa_draft</code> / <code>qa_answer</code>)에 둔다.'
          . ' 회원용 API 는 <code>qa_answer</code> 만 SELECT 한다 —'
          . ' <b>검수 없이 공개되는 경로가 구조적으로 없다.</b>',
    'shot' => 'adm-qna-list', 'adm' => '/adm/exam_qna_list.php',
  ),
  array(
    'id' => 'draft', 'ready' => false,
    'h'  => '답변 초안 일괄 생성',
    'p'  => '검수 화면을 열 때 서버가 LLM 을 호출해 초안을 만들어 두고, 관리자는 몰아서 승인한다.',
    'why'=> '컬럼·상태·검수 화면은 이미 있다. <b>모델을 붙이지 않았다</b> —'
          . ' 되는 것처럼 적지 않기로 했다.',
    'shot' => '', 'adm' => '',
  ),
  array(
    'id' => 'import', 'ready' => true,
    /* ⚠ '웹에서 즉시 수정' 이라고 쓰지 않는다 — 편집 화면(exam_problem_form.php)이 아직 없다.
         `edited_by` 보호 장치는 있지만 그걸 채우는 화면이 없다. 되는 것만 적는다. */
    'h'  => '문제 일괄 등록 · 변경분만 갱신',
    'p'  => 'problems.json 을 업로드하면 신규·갱신·건너뜀·실패가 집계되어 나온다.'
          . ' phpMyAdmin 도 SSH 도 필요 없다.',
    'why'=> '<code>pr_hash</code>(콘텐츠 md5)로 <b>변경분만</b> UPDATE 한다 —'
          . ' 300건 중 3건만 바뀌면 3건만 나가고, <code>pr_id</code> 가 유지되므로'
          . ' <b>회원 오답노트와 정답률 집계가 끊기지 않는다.</b><br>'
          . '재임포트가 <code>rd_free</code>(무료 회차)·<code>pr_open</code>(숨김) 설정을'
          . ' 건드리지 않는다 — 운영 중에 다시 올려도 정책이 유지된다.',
    'shot' => 'adm-import', 'adm' => '/adm/exam_import.php',
  ),
  array(
    'id' => 'quality', 'ready' => true,
    'h'  => '실 정답률로 문제 오류 자동 발견',
    'p'  => '정답률이 낮은 문항이 목록 맨 위로 온다. 4지선다에서 찍어도 25% 는 맞으므로'
          . ' <b>20% 미만은 통계적으로 이상하다</b> — 정답 자체가 틀렸을 가능성이 가장 크다.'
          . ' 이용자 신고를 기다리지 않고 응시 데이터로 먼저 찾는다.',
    'why'=> '문제를 DB 에 넣어서 얻은 것이다 — <code>ex_attempt_item</code> 의'
          . ' <code>(pr_id, is_ok)</code> 인덱스로 <code>GROUP BY</code> 한 번이면 나온다.'
          . ' 정적 파일이면 답안과 조인할 대상이 없어 <b>오류를 신고로만</b> 알 수 있다.<br>'
          . '오류를 찾으면 <b>즉시 내릴 수 있다</b>(<code>pr_open = 0</code>) —'
          . ' 고치는 데는 시간이 걸리고 그 사이에도 이용자는 계속 그 문제를 만난다.'
          . ' 이미 쌓인 채점 기록은 지우지 않으므로 과거 성적표가 깨지지 않는다.',
    'shot' => 'adm-problem-list', 'adm' => '/adm/exam_problem_list.php',
  ),
  array(
    'id' => 'credit', 'ready' => true,
    'h'  => '수강·포인트 문제집 단위 분리',
    'p'  => '수강 신청 승인 → 구독권 + 첫 달 포인트가 한 번에 반영된다. 포인트는 문제집별이라'
          . ' SQLD 를 승인해도 다른 문제집 잔액은 늘지 않는다.',
    'why'=> '원장이 append-only 라 <b>언제든 대조된다</b>. 화면 상단에 정합성이 한 줄로 뜬다.'
          . ' 같은 달 중복 지급은 <code>uq_month</code> 유니크 제약이 <b>DB 차원에서</b> 막는다 —'
          . ' 코드로 막으면 동시 요청에서 새어나간다.',
    'shot' => 'adm-credit-grant', 'adm' => '/adm/exam_credit_grant.php',
  ),
  array(
    'id' => 'multipd', 'ready' => true,
    'h'  => '자격증 추가 = DB 1행 (코드 변경 0)',
    'p'  => '문제집을 하나 늘리는 데 필요한 것은 <code>ex_product</code> 1행과 문제 임포트다.'
          . ' 화면·API·결제·포인트가 그대로 따라온다.',
    'why'=> '문제집별 데이터가 <code>pd/&lt;문제집&gt;/</code> 로 갈라져 있고 과목게시판 이름도'
          . ' 규칙으로 정해진다. <b>PHP 파일을 하나도 고치지 않는다.</b>',
    'shot' => 'adm-board-sync', 'adm' => '/adm/exam_board_sync.php',
  ),
);
?>

<link rel="stylesheet" href="<?php echo G5_URL ?>/exam/assets/mypage.css?v=<?php echo $fv('assets/mypage.css') ?>">
<link rel="stylesheet" href="<?php echo G5_URL ?>/exam/assets/features.css?v=<?php echo $fv('assets/features.css') ?>">

<div class="fe">

  <div class="crumb-bar"><div class="wrap">
    <div class="crumb">
      <a href="<?php echo G5_URL ?>/exam/"><?php echo htmlspecialchars($EX_BRAND) ?></a>
      <span class="sep">›</span><b>기능 소개</b>
    </div>
  </div></div>

  <div class="mp-head">
    <div>
      <h2>기능 소개 — 운영·도입</h2>
      <p class="mp-sub">문제집을 운영하는 쪽에서 무엇이 준비돼 있는가.
        수험생 화면은 <a href="<?php echo G5_URL ?>/exam/report.php?sample=1<?php
          echo $pd1 !== '' ? '&amp;pd=' . urlencode($pd1) : '' ?>">성적표 샘플</a>에서 바로 볼 수 있습니다.</p>
    </div>
    <div class="mp-actions">
      <a class="mp-btn" href="<?php echo G5_URL ?>/exam/<?php
         echo $pd1 !== '' ? 'check.php?pd=' . urlencode($pd1) : '' ?>">문제 풀러 가기</a>
      <a class="mp-btn ghost" href="<?php echo G5_BBS_URL ?>/qalist.php">도입 문의</a>
    </div>
  </div>

  <?php /* 목차 — 푸터에서 #앵커로 뛰어오므로, 어디에 떨어졌는지 보이게 한다 */ ?>
  <nav class="fe-toc">
    <?php foreach ($FEAT as $f) { ?>
      <a href="#<?php echo $f['id'] ?>"><?php echo htmlspecialchars(strip_tags($f['h'])) ?><?php
        if (!$f['ready']) echo ' <em>준비 중</em>' ?></a>
    <?php } ?>
  </nav>

<?php foreach ($FEAT as $i => $f) {
    $shot_rel = $f['shot'] !== '' ? 'assets/shots/' . $f['shot'] . '.png' : '';
    $has_shot = $shot_rel !== '' && is_readable(G5_PATH . '/exam/' . $shot_rel);
?>
  <section class="fe-card<?php echo $f['ready'] ? '' : ' soon' ?>" id="<?php echo $f['id'] ?>">
    <div class="fe-txt">
      <div class="fe-n"><?php echo $i + 1 ?><?php
        if (!$f['ready']) { ?><span class="fe-soon">준비 중</span><?php } ?></div>
      <h3><?php echo $f['h'] ?></h3>
      <p><?php echo $f['p'] ?></p>
      <p class="fe-why"><?php echo $f['why'] ?></p>
      <?php /* 관리자에게만 실제 화면 링크. 방문자에게 보이면 로그인 벽으로 튕긴다. */ ?>
      <?php if ($f['adm'] !== '' && $is_admin) { ?>
        <a class="fe-adm" href="<?php echo G5_URL . $f['adm'] ?>">관리자 화면 열기 →</a>
      <?php } ?>
    </div>

    <div class="fe-shot">
      <?php if ($has_shot) { ?>
        <img src="<?php echo G5_URL ?>/exam/<?php echo $shot_rel ?>?v=<?php echo $fv($shot_rel) ?>"
             alt="<?php echo htmlspecialchars(strip_tags($f['h'])) ?> 화면" loading="lazy">
      <?php } elseif ($f['ready']) { ?>
        <?php /* 자리표시 — 무엇을 어디에 넣어야 하는지 화면이 직접 말한다.
                 관리자에게만 파일 경로를 보여준다(방문자에게는 의미 없는 정보다). */ ?>
        <div class="fe-ph">
          <b>화면 캡처 자리</b>
          <?php if ($is_admin) { ?>
            <code>/exam/assets/shots/<?php echo $f['shot'] ?>.png</code>
            <span><?php echo htmlspecialchars($f['adm']) ?> 를 캡처해 이 경로로 올리면 자동으로 들어갑니다</span>
          <?php } else { ?>
            <span>준비 중입니다</span>
          <?php } ?>
        </div>
      <?php } else { ?>
        <div class="fe-ph off"><b>아직 만들지 않았습니다</b>
          <span>컬럼·상태·검수 화면만 준비돼 있습니다</span></div>
      <?php } ?>
    </div>
  </section>
<?php } ?>

</div>

<?php
include_once(G5_PATH . '/tail.php');
