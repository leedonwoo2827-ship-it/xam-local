<?php
/**
 * /exam/buy.php — 수강 신청
 *
 * ⚠ 결제를 붙이지 않는다. 내부 오픈 + 관리자 강제 크레딧 지급이 실운영 경로다.
 *   여기서는 **신청서를 받고 ex_order 에 pending 으로 남기는 것까지**만 한다.
 *   관리자가 adm/exam_orders.php 에서 승인 → 크레딧 지급 (그 화면은 아직 없다).
 *   PG 전환은 od_method 를 'manual' → 'pg' 로 바꾸는 것이 코드 변경의 전부다.
 *
 * ⚠ "미사용 질문은 매월 소멸" 고지 + 별도 동의를 받는다.
 *   소멸이 실질 수익원이라 법·윤리 양쪽 문제다(COST.md §8).
 *   동의 시각은 ex_user_ext.agree_at 에 기록한다.
 */
include_once('../common.php');

/* ── 문제집 확정 ────────────────────────────────────────────────────────────
 * 형식 검증만으로는 부족하다 — 'zzz' 도 정규식을 통과해 살아 있는 품목처럼 행동한다.
 * **ex_product 에 실재하는지** 확인하고, 없으면 첫 노출 품목으로 떨어뜨린다.
 * (api/_boot.php 의 ex_pd() 도 형식만 본다. 그쪽은 API 라 404 를 주면 되지만
 *  여기는 화면이라 빈 신청서를 보여주는 것보다 기본 문제집을 보여주는 게 낫다.)
 */
$pd_want = preg_match('/^[a-z0-9\-]{1,20}$/', isset($_GET['pd']) ? $_GET['pd'] : '')
         ? $_GET['pd'] : '';

$pd = '';
if ($pd_want !== '') {
    $r = sql_fetch("select pd_id from ex_product
                     where pd_id = '" . sql_real_escape_string($pd_want) . "' and pd_open = 1");
    if ($r) $pd = $r['pd_id'];
}
if ($pd === '') {
    $r = sql_fetch("select pd_id from ex_product where pd_open = 1 order by pd_sort, pd_id limit 1");
    $pd = $r ? $r['pd_id'] : '';
}

$msg = ''; $err = ''; $done = 0;

/* ── 제출 ──────────────────────────────────────────────────────────── */
if ($_SERVER['REQUEST_METHOD'] === 'POST') {

    if (!$is_member) {
        $err = '로그인 후 신청할 수 있습니다.';
    } elseif (function_exists('check_admin_token') && false) {
        // 관리자 토큰 체계는 adm/ 전용이다. 여기서는 쓰지 않는다.
    } else {
        $pl_id  = (int)(isset($_POST['pl_id']) ? $_POST['pl_id'] : 0);
        $name   = trim(isset($_POST['ax_name']) ? $_POST['ax_name'] : '');
        $tel    = trim(isset($_POST['ax_tel'])  ? $_POST['ax_tel']  : '');
        $memo   = trim(isset($_POST['ax_memo']) ? $_POST['ax_memo'] : '');
        $agree  = !empty($_POST['ax_agree']);

        /* ★ pd_id 를 조건에 넣는다. 없으면 ?pd=bdae-w 화면에서 pl_id=1(sqld) 을 제출해
         *   "빅데이터 신청인데 SQLD 과정" 인 고아 주문이 만들어진다.
         *   화면에 안 보이는 값이라도 POST 는 조작 가능하다 — 서버에서 교차 검증한다. */
        $plan = ($pl_id && $pd !== '')
              ? sql_fetch("select * from ex_plan
                            where pl_id = " . $pl_id . "
                              and pd_id = '" . sql_real_escape_string($pd) . "'
                              and pl_open = 1")
              : null;

        if (!$plan)                       $err = '수강 과정을 선택해 주십시오.';
        elseif (mb_strlen($name) < 2)     $err = '이름을 입력해 주십시오.';
        elseif (!preg_match('/^[0-9\-\s]{9,20}$/', $tel)) $err = '연락처를 확인해 주십시오.';
        elseif (!$agree)                  $err = '질문권 소멸 조항에 동의해야 신청할 수 있습니다.';
        else {
            $mb  = sql_real_escape_string($member['mb_id']);
            $now = G5_TIME_YMDHIS;

            /* ★★ 중복 검사에 pd_id 를 넣는다 ★★
             *
             * 이 조건이 없던 것이 다품목 전환의 가장 큰 걸림돌이었다.
             * mb_id + pending 만 보면 SQLD 를 신청해 승인 대기 중인 회원은
             * **빅데이터를 아예 신청할 수 없다** — "이미 접수된 신청이 있습니다"로 막힌다.
             * 문제집별로 따로 수강하는 구조에서는 문제집마다 1건씩 대기할 수 있어야 한다. */
            $pdq = sql_real_escape_string($pd);
            $dup = sql_fetch("select od_id from ex_order
                               where mb_id = '$mb' and pd_id = '$pdq' and od_status = 'pending'
                               order by od_id desc limit 1");
            if ($dup) {
                $err = '이 문제집에 이미 접수된 신청이 있습니다(신청번호 ' . (int)$dup['od_id'] . '). 승인 후 다시 신청해 주십시오.';
            } else {
                sql_query("insert into ex_order
                              (mb_id, pd_id, pl_id, od_price, od_months, od_quota, od_method,
                               od_depositor, od_status, admin_memo, created_at)
                           values ('$mb', '$pdq', " . (int)$plan['pl_id'] . ", " . (int)$plan['pl_price'] . ",
                                   " . (int)$plan['pl_months'] . ", " . (int)$plan['pl_quota'] . ",
                                   'manual', '" . sql_real_escape_string($name) . "', 'pending',
                                   '" . sql_real_escape_string(mb_substr($tel . ' / ' . $memo, 0, 250)) . "',
                                   '$now')", false);
                $od_id = (int)sql_insert_id();

                if ($od_id) {
                    // ex_user_ext 없으면 만들고, 소멸 조항 동의 시각을 남긴다
                    $ext = sql_fetch("select mb_id from ex_user_ext where mb_id = '$mb'");
                    if (!$ext) {
                        sql_query("insert into ex_user_ext (mb_id, agree_at, created_at)
                                        values ('$mb', '$now', '$now')", false);
                    } else {
                        sql_query("update ex_user_ext set agree_at = '$now' where mb_id = '$mb'", false);
                    }
                    $done = $od_id;
                } else {
                    $err = '접수에 실패했습니다. 잠시 후 다시 시도해 주십시오.';
                }
            }
        }
    }
}

/* ── 데이터 ────────────────────────────────────────────────────────── */
$prod  = sql_fetch("select * from ex_product where pd_id = '" . sql_real_escape_string($pd) . "'");

/* ★ 이 문제집의 과정만. pd_id 조건이 없으면 두 문제집의 과정 6개가 한 화면에 뜨고,
 *   첫 항목이 자동 선택되므로 ?pd=bdae-w 인데 SQLD 과정이 기본값이 된다. */
$plans = array();
$res = sql_query("select * from ex_plan
                   where pd_id = '" . sql_real_escape_string($pd) . "' and pl_open = 1
                   order by pl_sort, pl_id", false);
while ($r = sql_fetch_array($res)) $plans[] = $r;

/* 다른 문제집으로 갈아타는 링크용. 노출 중인 것만. */
$others = array();
$res = sql_query("select pd_id, pd_name from ex_product
                   where pd_open = 1 and pd_id <> '" . sql_real_escape_string($pd) . "'
                   order by pd_sort, pd_id", false);
while ($r = sql_fetch_array($res)) $others[] = $r;

// 0 이면 아래 floor($quota / $unit) 이 0으로 나누기가 된다
$unit = ($prod && (int)$prod['cost_units'] > 0) ? (int)$prod['cost_units'] : 10;

$g5['title'] = '수강 신청';
include_once(G5_PATH . '/head.php');
?>

<link rel="stylesheet" href="<?php echo G5_URL ?>/exam/assets/mypage.css?v=<?php echo @filemtime(G5_PATH.'/exam/assets/mypage.css') ?>">

<div class="apply">

<?php if ($done) { ?>
  <div class="ap-done">
    <div class="ap-done-ic">✓</div>
    <h2>신청이 접수되었습니다</h2>
    <p>신청번호 <b>#<?php echo $done ?></b></p>
    <p class="ap-done-sub">
      담당자가 확인 후 승인하면 질문권이 지급됩니다.<br>
      승인 전에도 <b>문제 풀이와 해설은 모두 이용하실 수 있습니다.</b>
    </p>
    <div class="ap-done-btns">
      <a class="mp-btn" href="<?php echo G5_URL ?>/exam/check.html?pd=<?php echo urlencode($pd) ?>">문제 풀러 가기</a>
      <a class="mp-btn ghost" href="<?php echo G5_URL ?>/exam/mypage.php">마이페이지</a>
    </div>
  </div>
<?php } else { ?>

  <div class="mp-head">
    <div>
      <h2><?php echo htmlspecialchars($prod ? $prod['pd_name'] : strtoupper($pd)) ?> 수강 신청</h2>
      <p class="mp-sub">신청 후 담당자 승인으로 질문권이 지급됩니다.</p>
    </div>
  </div>

  <?php if ($others) { ?>
  <?php /* 문제집별로 따로 수강하는 구조라, 지금 보고 있는 것이 무엇이고 다른 무엇이 있는지
           같은 자리에서 보여준다. 없으면 이용자가 URL 을 고쳐야 다른 문제집을 신청할 수 있다. */ ?>
  <div class="ap-pdbar">
    <span class="ap-pdbar-l">다른 문제집</span>
    <?php foreach ($others as $o) { ?>
      <a class="ap-pdchip" href="?pd=<?php echo urlencode($o['pd_id']) ?>"><?php echo htmlspecialchars($o['pd_name']) ?></a>
    <?php } ?>
  </div>
  <?php } ?>

  <?php if ($err) { ?><div class="ap-err"><?php echo htmlspecialchars($err) ?></div><?php } ?>

  <?php if (!$is_member) { ?>
    <div class="ap-login">
      <p>신청하려면 로그인이 필요합니다.</p>
      <a class="mp-btn" href="<?php echo G5_BBS_URL ?>/login.php?url=<?php echo urlencode(G5_URL.'/exam/buy.php?pd='.$pd) ?>">로그인</a>
      <a class="mp-btn ghost" href="<?php echo G5_BBS_URL ?>/register.php">회원가입</a>
    </div>
  <?php } ?>

  <div class="ap-grid">
    <!-- 좌: 안내 -->
    <div class="ap-info">
      <h3>포함되는 것</h3>
      <ul class="ap-list">
        <li><b>문제 <?php echo $prod ? '300' : '—' ?>제 · 6회차</b><br>정답과 해설 전문. 회원가입 없이도 볼 수 있습니다.</li>
        <li><b>서버 채점 · 오답노트</b><br>틀린 문제가 쌓이고 몇 번 틀렸는지 남습니다.</li>
        <li><b>1:1 질문</b><br>문제를 풀다 막히면 그 자리에서 질문합니다. <u>여기가 수강 신청으로 열리는 부분입니다.</u></li>
        <li><b>해설 영상 · 이론 요약노트</b></li>
      </ul>

      <h3>질문권</h3>
      <p class="ap-p">
        질문 1건에 질문권 1개를 씁니다.
        <b>매월 지급되고, 그 달에 쓰지 않은 질문권은 다음 달로 이월되지 않습니다.</b>
      </p>
      <p class="ap-note">
        ※ 현재는 내부 오픈 기간이라 질문권을 차감하지 않습니다.
        차감이 시작되면 공지로 먼저 알려드립니다.
      </p>
    </div>

    <!-- 우: 신청 폼 -->
    <form class="ap-form" method="post">
      <h3>신청서</h3>

      <div class="ap-field">
        <label>수강 과정</label>
        <div class="ap-plans">
          <?php foreach ($plans as $i => $p) { ?>
          <label class="ap-plan">
            <input type="radio" name="pl_id" value="<?php echo (int)$p['pl_id'] ?>" <?php echo $i === 0 ? 'checked' : '' ?>>
            <span class="ap-plan-in">
              <b><?php echo htmlspecialchars($p['pl_name']) ?></b>
              <em><?php echo number_format((int)$p['pl_price']) ?>원</em>
              <small>매월 질문 <?php echo (int)floor($p['pl_quota'] / max(1, $unit)) ?>개 · <?php echo (int)$p['pl_months'] ?>개월</small>
            </span>
          </label>
          <?php } ?>
          <?php if (!$plans) { ?><p class="ap-note">등록된 과정이 없습니다. 관리자에게 문의해 주십시오.</p><?php } ?>
        </div>
      </div>

      <div class="ap-field">
        <label for="ax_name">이름</label>
        <input type="text" id="ax_name" name="ax_name" maxlength="20" required
               value="<?php echo $is_member ? htmlspecialchars($member['mb_name']) : '' ?>">
      </div>

      <div class="ap-field">
        <label for="ax_tel">연락처</label>
        <input type="tel" id="ax_tel" name="ax_tel" maxlength="20" placeholder="010-0000-0000" required
               value="<?php echo $is_member ? htmlspecialchars($member['mb_hp']) : '' ?>">
      </div>

      <div class="ap-field">
        <label for="ax_memo">남길 말 <span class="opt">선택</span></label>
        <textarea id="ax_memo" name="ax_memo" rows="3" maxlength="200"
                  placeholder="소속·목표 시험일 등"></textarea>
      </div>

      <label class="ap-agree">
        <input type="checkbox" name="ax_agree" value="1" required>
        <span><b>미사용 질문권은 매월 소멸되며 다음 달로 이월되지 않습니다.</b> 위 내용에 동의합니다.</span>
      </label>

      <button type="submit" class="ap-submit" <?php echo $is_member ? '' : 'disabled' ?>>
        <?php echo $is_member ? '신청하기' : '로그인 후 신청할 수 있습니다' ?>
      </button>
      <p class="ap-note">지금은 결제 없이 접수만 됩니다. 담당자 승인 후 질문권이 지급됩니다.</p>
    </form>
  </div>

<?php } ?>
</div>

<?php
include_once(G5_PATH . '/tail.php');
