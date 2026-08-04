<?php
/**
 * 질문 검수 — 답변 작성.
 *
 * 왼쪽에 문제 본문(정답·해설 포함), 오른쪽에 질문과 답변 입력.
 * 두 개를 나란히 두는 게 이 화면의 전부다 — 문제를 다시 찾아보게 만들면 검수가 느려진다.
 *
 * 동작
 *   저장     qa_answer 만 저장. 상태를 바꾸지 않는다(초안 다듬는 중)
 *   승인     qa_status='approved' + qa_answered_at → **이용자에게 공개된다**
 *   반려     qa_status='rejected' + 포인트 환불(cost_units) + qa_refunded=1
 *   초안 복사 qa_draft 를 답변란으로. LLM 이 붙은 뒤(S8) 쓰는 버튼이다
 *
 * ★ qa_draft 를 읽는 유일한 화면이다. 회원 API 는 그 컬럼을 SELECT 하지 않는다.
 *   검수 없이 초안이 새어나가는 경로를 구조적으로 없앤 장치다(api/qna.php 머리 주석).
 */
$sub_menu = '600200';
require_once './_common.php';

auth_check_menu($auth, $sub_menu, 'r');

require_once G5_PATH . '/exam/api/lib/credit.php';
require_once './exam_lib/prompt.php';      // ex_draft_one()
require_once './exam_lib/board_qna.php';   // exbq_answer_to_board()

$qa_id = (int)(isset($_REQUEST['qa_id']) ? $_REQUEST['qa_id'] : 0);
$msg = ''; $err = '';

/* ── 처리 ──────────────────────────────────────────────────────────────── */
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    auth_check_menu($auth, $sub_menu, 'w');
    if (function_exists('check_admin_token')) check_admin_token();
    else                                     check_token();

    $act    = isset($_POST['act']) ? $_POST['act'] : '';
    $answer = isset($_POST['qa_answer']) ? trim($_POST['qa_answer']) : '';
    $public = !empty($_POST['qa_public']) ? 1 : 0;

    $q = $qa_id ? sql_fetch("select * from ex_qna where qa_id = " . $qa_id) : null;

    if (!$q) {
        $err = '질문을 찾을 수 없습니다.';
    } elseif ($act === 'save' || $act === 'approve') {
        if ($act === 'approve' && mb_strlen($answer, 'UTF-8') < 5) {
            $err = '답변을 5자 이상 적어야 승인할 수 있습니다.';
        } else {
            $set = "qa_answer = '" . sql_real_escape_string($answer) . "',
                    qa_public = " . $public . ",
                    edited_by = '" . sql_real_escape_string($member['mb_id']) . "'";
            if ($act === 'approve') {
                // 답변 시각은 처음 승인할 때만 찍는다. 재승인(수정)으로 덮으면
                // "며칠 기다렸나"를 알 수 없게 된다.
                $set .= ", qa_status = 'approved'";
                if (empty($q['qa_answered_at'])) $set .= ", qa_answered_at = '" . G5_TIME_YMDHIS . "'";
            }
            sql_query("update ex_qna set $set where qa_id = " . $qa_id, false);
            $msg = ($act === 'approve')
                 ? '승인했습니다. 이용자에게 공개됩니다.'
                 : '저장했습니다. (상태는 그대로 — 승인해야 공개됩니다)';

            /* ★ 게시판에서 온 질문이면 게시판에도 답을 달아야 한다.
             *
             *   질문자는 게시판에 글을 썼고 알림·목록을 거기서 본다. 우리 DB 에만
             *   답이 들어가면 그 사람 입장에서는 **아무 일도 일어나지 않은 것**이다.
             *   (문제풀이 화면 넷째 탭의 '답변완료' 뱃지도 ex_qna 를 보므로 켜지지만,
             *    정작 글을 열면 댓글이 없다 — 그게 더 나쁘다.)
             *
             *   재승인(오타 수정)이면 기존 댓글 내용을 갈아 끼운다. qa_reply_wr_id 를
             *   들고 있어서 가능하다 — 없으면 답이 두 개 붙는다.
             *
             *   실패는 삼키지 않는다. 승인은 이미 됐으므로 되돌리지 않고, 대신 화면에
             *   그대로 알려 수동으로 처리하게 한다.
             */
            if ($act === 'approve') {
                $rb = exbq_answer_to_board($qa_id, $member['mb_id']);
                if (!empty($rb['ok'])) {
                    $msg .= !empty($rb['updated'])
                          ? ' 게시판 답변 댓글도 갱신했습니다.'
                          : ' 게시판에 답변 댓글을 달았습니다.';
                } elseif (empty($rb['skip'])) {
                    $err = '승인은 됐지만 게시판 댓글에 실패했습니다 — ' . $rb['msg']
                         . ' 게시판에서 직접 답글을 달아 주십시오.';
                }
            }
        }

    } elseif ($act === 'draft') {
        /* 단건 초안 생성. 목록의 일괄과 같은 함수를 쓴다 — 두 경로가 갈리면
           한쪽만 고쳐지는 일이 생긴다. */
        @set_time_limit(0);
        $r = ex_draft_one($qa_id, $member['mb_id']);
        if (!empty($r['ok'])) {
            $msg = '초안을 만들었습니다 · 원가 ' . number_format((float)$r['cost'], 4) . '원'
                 . (!empty($r['over_cap']) ? ' (원가 상한 초과 — 모델·프롬프트를 확인하십시오)' : '')
                 . '. 아래 초안을 읽고 [초안을 답변란으로 복사] 하십시오.';
        } else {
            $err = $r['msg'];
        }

    } elseif ($act === 'reject') {
        $reason = trim(isset($_POST['reason']) ? $_POST['reason'] : '');
        if ($reason === '') {
            $err = '반려 사유를 적어 주십시오. 이용자에게 그대로 보입니다.';
        } elseif ($q['qa_status'] === 'rejected') {
            $err = '이미 반려된 질문입니다.';
        } else {
            /* 반려 순서: 상태를 먼저 바꾸고(조건부) → 환불.
             * 조건부 UPDATE 라 두 번 눌러도 한 번만 통과하므로 이중 환불이 안 생긴다.
             * ex_credit_refund 도 lg_ref 로 중복을 막지만 방어선을 둘 둔다. */
            sql_query("update ex_qna
                          set qa_status = 'rejected',
                              qa_answer = '" . sql_real_escape_string($reason) . "',
                              qa_answered_at = '" . G5_TIME_YMDHIS . "',
                              edited_by = '" . sql_real_escape_string($member['mb_id']) . "'
                        where qa_id = " . $qa_id . " and qa_status <> 'rejected'", false);

            if (ex_affected() !== 1) {
                $err = '이미 처리된 질문입니다.';
            } else {
                $cost = (int)$q['cost_units'];
                if ($cost > 0 && !(int)$q['qa_refunded']) {
                    $ok = ex_credit_refund($q['mb_id'], $q['pd_id'], $cost,
                                           'qna:' . $qa_id, '질문 반려 환불', $member['mb_id']);
                    if ($ok) {
                        sql_query("update ex_qna set qa_refunded = 1 where qa_id = " . $qa_id, false);
                        $msg = '반려하고 ' . number_format($cost) . '원을 환불했습니다.';
                    } else {
                        // 환불이 실패하면 그 사실을 반드시 화면에 남긴다 — 조용히 넘기면 민원이 된다
                        $err = '반려했으나 환불에 실패했습니다. 포인트 지급 화면에서 수동으로 처리하십시오.';
                    }
                } else {
                    $msg = '반려했습니다.' . ($cost === 0 ? ' (무료 질문이라 환불 없음)' : ' (이미 환불됨)');
                }
            }
        }

    } elseif ($act === 'reopen') {
        // 잘못 승인·반려한 것을 되돌린다. 환불은 되돌리지 않는다(원장을 뒤집지 않는다).
        sql_query("update ex_qna set qa_status = 'pending', qa_answered_at = null
                    where qa_id = " . $qa_id, false);
        $msg = '대기 상태로 되돌렸습니다. 환불은 되돌리지 않습니다 — 원장은 수정하지 않습니다.';
    }
}

/* ── 조회 ──────────────────────────────────────────────────────────────── */
$q = $qa_id ? sql_fetch("select q.*, d.pd_name, m.mb_nick, m.mb_email
                           from ex_qna q
                           left join ex_product d on d.pd_id = q.pd_id
                           left join g5_member  m on m.mb_id = q.mb_id
                          where q.qa_id = " . $qa_id) : null;

$prob = null; $sj_name = '';
if ($q) {
    if ($q['pr_key'] !== '') {
        $prob = sql_fetch("select * from ex_problem
                            where pd_id = '" . sql_real_escape_string($q['pd_id']) . "'
                              and pr_key = '" . sql_real_escape_string($q['pr_key']) . "'");
    }
    if ($prob)                        $sj_name = $prob['sj_name'];
    elseif ((int)$q['sj_no'] > 0) {
        $s = sql_fetch("select sj_name from ex_problem
                         where pd_id = '" . sql_real_escape_string($q['pd_id']) . "'
                           and sj_no = " . (int)$q['sj_no'] . " limit 1");
        if ($s) $sj_name = $s['sj_name'];
    }
}

/* 같은 문제에 달린 다른 공개 답변 — 중복 답변을 막는 장치다.
 * 이용자 쪽에서도 질문 폼 전에 이걸 먼저 보여준다(api/qna.php ?keys=). */
$siblings = array();
if ($q && $q['pr_key'] !== '') {
    $res = sql_query("select qa_id, qa_question, qa_answer, qa_answered_at
                        from ex_qna
                       where pr_key = '" . sql_real_escape_string($q['pr_key']) . "'
                         and qa_status = 'approved' and qa_id <> " . $qa_id . "
                       order by qa_answered_at desc limit 5", false);
    while ($r = sql_fetch_array($res)) $siblings[] = $r;
}

$bal = ($q && $q['mb_id'] !== '') ? ex_credit_balance($q['mb_id'], $q['pd_id']) : 0;

$g5['title'] = '질문 답변';
require_once './admin.head.php';

function exf_h($s) { return htmlspecialchars((string)$s, ENT_QUOTES, 'UTF-8'); }

$CIRC = array('①','②','③','④','⑤','⑥','⑦','⑧','⑨','⑩');
$ST   = array('pending' => '대기', 'drafting' => '초안 생성 중', 'draft_ready' => '검수 대기',
              'approved' => '완료', 'rejected' => '반려');
?>

<style>
.exf{max-width:1340px}
.exf .box{background:#fff;border:1px solid #e3e6ec;border-radius:8px;padding:16px 18px;margin:0 0 14px}
.exf h2{font-size:14.5px;margin:0 0 10px;font-weight:700}
.exf .msg{padding:11px 16px;border-radius:6px;margin:0 0 14px;font-size:14px;line-height:1.6}
.exf .msg.err{background:#fdeced;border:1px solid #c22638;color:#8c1220}
.exf .msg.good{background:#e9f7ef;border:1px solid #0a7f3f;color:#075c2d}
.exf .grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;align-items:start}
@media (max-width:1100px){.exf .grid{grid-template-columns:1fr}}
.exf .pill{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:700}
.exf .pill.wait{background:#fff6e5;color:#8a5a00}
.exf .pill.rev{background:#e8efff;color:#1b3faa}
.exf .pill.ok{background:#e9f7ef;color:#075c2d}
.exf .pill.no{background:#f2f3f5;color:#666}
.exf .tag{display:inline-block;padding:1px 8px;border:1px solid #e3e6ec;border-radius:4px;
  font-size:12px;color:#555;background:#fafbfc}
.exf .tag.red{border-color:#c22638;color:#c22638;background:#fdeced;font-weight:700}
.exf .head{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:12px}
.exf .qbody{background:#f7f9fc;border:1px solid #e3e6ec;border-radius:6px;padding:13px 15px;
  font-size:14px;line-height:1.75;white-space:pre-wrap;word-break:break-word}
.exf .pq{font-size:14.5px;line-height:1.75;margin:0 0 12px;white-space:pre-wrap}
.exf .opt{display:flex;gap:8px;padding:6px 9px;border:1px solid #eceff3;border-radius:5px;
  margin-bottom:5px;font-size:13.5px;line-height:1.6}
.exf .opt.ans{border-color:#0a7f3f;background:#f0faf4}
.exf .opt.chose{border-color:#c22638;background:#fdf1f2}
.exf .opt .n{font-weight:700;color:#666;flex:0 0 auto}
.exf .sql{background:#0f172a;color:#e2e8f0;padding:11px 13px;border-radius:6px;overflow-x:auto;
  font-family:Consolas,monospace;font-size:12.5px;line-height:1.65;margin:0 0 12px}
.exf .expl{background:#fffdf3;border:1px solid #eadfae;border-radius:6px;padding:11px 13px;
  font-size:13.5px;line-height:1.75;white-space:pre-wrap}
.exf textarea{width:100%;box-sizing:border-box;padding:11px 13px;border:1px solid #dde1e8;
  border-radius:6px;font-size:14px;line-height:1.75;font-family:inherit;resize:vertical}
.exf .acts{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:11px}
.exf .acts .grow{margin-left:auto}
.exf .draft{background:#eef3ff;border:1px solid #c9d8fb;border-radius:6px;padding:11px 13px;
  font-size:13.5px;line-height:1.75;white-space:pre-wrap;margin:0 0 8px}
.exf .hint{color:#666;font-size:12.5px;line-height:1.7}
.exf code{background:#f4f5f7;padding:1px 5px;border-radius:3px;font-family:Consolas,monospace}
.exf table.kv{border-collapse:collapse;width:100%;font-size:12.5px}
.exf .kv th,.exf .kv td{border:1px solid #e3e6ec;padding:5px 9px;text-align:left}
.exf .kv th{background:#f7f8fa;width:110px;font-weight:600;white-space:nowrap}
.exf .sib{border-top:1px solid #eceff3;padding:9px 0;font-size:13px;line-height:1.65}
.exf .sib b{color:#1b3faa}
.exf .chk{display:inline-flex;align-items:center;gap:6px;font-size:13px}
</style>

<div class="exf">

<?php if ($msg): ?><div class="msg good"><?php echo exf_h($msg) ?></div><?php endif; ?>
<?php if ($err): ?><div class="msg err"><?php echo exf_h($err) ?></div><?php endif; ?>

<?php if (!$q): ?>
  <div class="box"><p class="hint">질문을 찾을 수 없습니다.
    <a href="./exam_qna_list.php">목록으로</a></p></div>
<?php else: ?>

  <div class="box">
    <div class="head">
      <a class="tag" href="./exam_qna_list.php">← 목록</a>
      <b>#<?php echo (int)$q['qa_id'] ?></b>
      <?php
      $cls = array('pending'=>'wait','drafting'=>'wait','draft_ready'=>'rev',
                   'approved'=>'ok','rejected'=>'no');
      $c = isset($cls[$q['qa_status']]) ? $cls[$q['qa_status']] : ''; ?>
      <span class="pill <?php echo $c ?>"><?php
        echo exf_h(isset($ST[$q['qa_status']]) ? $ST[$q['qa_status']] : $q['qa_status']) ?></span>
      <span class="tag"><?php echo exf_h($q['pd_name'] ? $q['pd_name'] : $q['pd_id']) ?></span>
      <?php if ($sj_name): ?><span class="tag"><?php echo exf_h($sj_name) ?></span><?php endif; ?>
      <?php if ($q['kind'] === 'report'): ?><span class="tag red">오류 신고</span><?php endif; ?>
      <?php if ((int)$q['cost_units'] > 0 && !(int)$q['qa_credit_ok']): ?>
        <span class="tag red">차감 미확정</span>
      <?php endif; ?>
      <?php if ((int)$q['qa_refunded']): ?><span class="tag">환불됨</span><?php endif; ?>
    </div>

    <table class="kv">
      <tr><th>회원</th><td><?php echo exf_h($q['mb_nick'] ? $q['mb_nick'] : $q['mb_id']) ?>
        (<code><?php echo exf_h($q['mb_id']) ?></code>)
        <?php echo $q['mb_email'] ? ' · ' . exf_h($q['mb_email']) : '' ?>
        &nbsp;— 남은 질문 <b><?php echo (int)floor($bal / max(1, ex_credit_unit($q['pd_id']))) ?>개</b>
        <span class="hint">(<?php echo number_format($bal) ?>원)</span></td></tr>
      <tr><th>문제</th><td>
        <?php if ($q['pr_key']): ?>
          <code><?php echo exf_h($q['pr_key']) ?></code>
          <?php if ($prob): ?> — <?php echo (int)$prob['rd_no'] ?>회 <?php echo (int)$prob['pr_no'] ?>번
            <?php if (!(int)$prob['pr_open']): ?><span class="tag red">숨김 처리됨</span><?php endif; ?>
          <?php else: ?> <span class="tag red">문제를 찾을 수 없음</span><?php endif; ?>
        <?php else: ?>
          일반 질문 (문제 지정 없음)
        <?php endif; ?>
      </td></tr>
      <tr><th>포인트</th><td>
        <?php echo (int)$q['cost_units'] === 0
          ? '무료 (차감 없음 — 무료 기간에 받은 질문)'
          : number_format((int)$q['cost_units']) . '원 차감' ?>
      </td></tr>
      <tr><th>등록</th><td><?php echo exf_h($q['created_at']) ?>
        <?php if ($q['qa_answered_at']): ?> · 답변 <?php echo exf_h($q['qa_answered_at']) ?><?php endif; ?>
        <?php if ($q['edited_by']): ?> · 처리자 <?php echo exf_h($q['edited_by']) ?><?php endif; ?>
      </td></tr>
      <?php if ($q['bo_table'] && $q['wr_id']): ?>
      <tr><th>게시판</th><td>
        <a href="<?php echo G5_BBS_URL ?>/board.php?bo_table=<?php echo exf_h($q['bo_table']) ?>&amp;wr_id=<?php echo (int)$q['wr_id'] ?>"
           target="_blank"><?php echo exf_h($q['bo_table']) ?> #<?php echo (int)$q['wr_id'] ?></a>
        <span class="hint">— 과목게시판 글로 등록된 질문이다</span>
      </td></tr>
      <?php endif; ?>
    </table>
  </div>

  <div class="grid">

    <!-- 왼쪽: 문제 -->
    <div class="box">
      <h2>문제 <?php echo $prob ? '' : '<span class="hint">— 지정된 문제가 없습니다</span>' ?></h2>
      <?php if ($prob): ?>
        <?php if ($prob['passage']): ?>
          <div class="qbody" style="margin-bottom:12px"><?php echo exf_h($prob['passage']) ?></div>
        <?php endif; ?>
        <div class="pq"><?php echo exf_h($prob['question']) ?></div>
        <?php if ($prob['sql_text']): ?>
          <pre class="sql"><?php echo exf_h($prob['sql_text']) ?></pre>
        <?php endif; ?>
        <?php
        $ch = json_decode((string)$prob['choices_json'], true);
        if (is_array($ch)) {
            $ai = ($prob['answer_index'] === null) ? -1 : (int)$prob['answer_index'];
            $ci = (int)$q['qa_chosen'];
            foreach ($ch as $k => $t) {
                $cl = '';
                if ($k === $ai)      $cl = ' ans';
                elseif ($k === $ci)  $cl = ' chose';
                echo '<div class="opt' . $cl . '"><span class="n">'
                   . (isset($CIRC[$k]) ? $CIRC[$k] : ($k + 1)) . '</span><span>' . exf_h($t) . '</span>'
                   . ($k === $ai ? ' <span class="tag">정답</span>' : '')
                   . ($k === $ci && $k !== $ai ? ' <span class="tag red">질문자 선택</span>' : '')
                   . '</div>';
            }
        }
        ?>
        <?php if ($prob['explanation']): ?>
          <h2 style="margin-top:14px">해설</h2>
          <div class="expl"><?php echo exf_h($prob['explanation']) ?></div>
        <?php endif; ?>

        <div class="hint" style="margin-top:12px">
          해설이 이미 답을 담고 있으면 <b>해설을 인용해 답하고 끝낸다.</b> 새로 쓰지 않는다 —
          같은 내용을 두 번 쓰면 나중에 어긋난다. 해설 자체가 부족하면
          <b>문제 임포트 원본(<code>02/</code>)을 고치는 것이 근본 해결</b>이다.
        </div>
      <?php else: ?>
        <p class="hint">문제를 지정하지 않은 일반 질문입니다.
          과목만 골라 물어보는 경우가 많습니다 — 이용자는 "무슨 과목 몇 번"을 다 적기보다
          앞을 생략하는 쪽이 흔합니다.</p>
      <?php endif; ?>

      <?php if ($siblings): ?>
        <h2 style="margin-top:16px">이 문제의 다른 공개 답변 <span class="hint">— 중복 답변 방지</span></h2>
        <?php foreach ($siblings as $s): ?>
          <div class="sib">
            <b>Q</b> <?php echo exf_h($s['qa_question']) ?><br>
            <b>A</b> <?php echo exf_h(mb_strimwidth((string)$s['qa_answer'], 0, 300, '…', 'UTF-8')) ?>
            <div class="hint"><a href="?qa_id=<?php echo (int)$s['qa_id'] ?>">#<?php echo (int)$s['qa_id'] ?> 열기</a>
              · <?php echo exf_h(substr($s['qa_answered_at'], 0, 10)) ?></div>
          </div>
        <?php endforeach; ?>
      <?php endif; ?>
    </div>

    <!-- 오른쪽: 질문 · 답변 -->
    <div class="box">
      <h2>질문</h2>
      <div class="qbody"><?php echo exf_h($q['qa_question']) ?></div>

      <?php
      /* ── 초안 생성 버튼 ──
       * pending·draft_ready 일 때만 낸다. ex_draft_one() 이 그 두 상태만 집으므로
       * (원자적 잠금) 다른 상태에서 눌러도 "대상이 아닙니다" 로 떨어진다 —
       * 눌러도 안 되는 버튼을 보여주지 않는다.
       *
       * 문항이 연결됐는지를 버튼 옆에 적는다. 이게 초안 품질을 가장 크게 좌우하는데,
       * 만든 뒤에 알면 원가를 이미 쓴 뒤다. */
      $can_draft = in_array($q['qa_status'], array('pending', 'draft_ready'), true);
      $has_draft = ($q['qa_draft'] !== null && $q['qa_draft'] !== '');
      if ($can_draft):
      ?>
      <form method="post" style="margin-top:14px;padding-top:12px;border-top:1px solid #eceff3">
        <input type="hidden" name="token" value="">
        <input type="hidden" name="qa_id" value="<?php echo (int)$q['qa_id'] ?>">
        <input type="hidden" name="act" value="draft">
        <div class="acts">
          <button type="submit" class="btn_b01"
                  onclick="return confirm('LLM 초안을 만듭니다. 원가가 발생합니다.\n초안은 이용자에게 보이지 않습니다.');">
            <?php echo $has_draft ? '초안 다시 만들기' : '초안 생성' ?></button>
          <span class="hint">
            <?php if ($q['pr_key'] !== ''): ?>
              문항 <code><?php echo exf_h($q['pr_key']) ?></code> 연결됨 —
              발문·보기·정답·해설이 프롬프트에 들어갑니다.
            <?php else: ?>
              <b>문항이 연결되지 않았습니다.</b> 과목 정보만으로 초안을 만들어 품질이 떨어집니다 —
              게시판 제목에 <code>1회 61번</code> 같은 표식이 있으면 자동으로 붙습니다.
            <?php endif; ?>
          </span>
        </div>
      </form>
      <?php endif; ?>

      <?php if ($q['qa_draft'] !== null && $q['qa_draft'] !== ''): ?>
        <h2 style="margin-top:16px">LLM 초안
          <span class="hint">— 이용자에게 보이지 않는다. 승인한 답변만 공개된다</span></h2>
        <?php
        /* ★ 초안을 **렌더해서** 보여준다. 초안이 `**굵게**` 를 쓰는데 그대로 두면
             별표가 글자로 보여 읽기가 나쁘다(강조가 아니라 noise 다).
           ★ 그런데 [초안을 답변란으로 복사] 는 **원문**을 넣어야 한다. 렌더된 것을
             textContent 로 긁으면 별표가 사라져서, 승인 뒤 게시판·마이페이지에서
             강조가 통째로 빠진다. 그래서 원문을 data-raw 에 따로 실어 둔다. */
        require_once G5_PATH . '/exam/lib/md.php';
        ?>
        <div class="draft" id="draftBox"
             data-raw="<?php echo exf_h($q['qa_draft']) ?>"><?php
          echo ex_md_html($q['qa_draft']) ?></div>
        <div class="hint">
          모델 <code><?php echo exf_h($q['qa_model'] ? $q['qa_model'] : '—') ?></code> ·
          토큰 in <?php echo (int)$q['qa_tok_in'] ?> / cache <?php echo (int)$q['qa_tok_cache'] ?>
          / out <?php echo (int)$q['qa_tok_out'] ?> ·
          원가 <?php echo exf_h($q['qa_cost']) ?>원
          <?php
          $cap = sql_fetch("select cost_cap from ex_product where pd_id = '" . sql_real_escape_string($q['pd_id']) . "'");
          if ($cap && (float)$q['qa_cost'] > (float)$cap['cost_cap']): ?>
            <span class="tag red">원가 상한(<?php echo exf_h($cap['cost_cap']) ?>원) 초과</span>
          <?php endif; ?>
        </div>
        <button type="button" class="btn_b01" style="margin-top:8px"
                onclick="document.getElementById('ansBox').value=(document.getElementById('draftBox').dataset.raw||'').trim();">
          초안을 답변란으로 복사
        </button>
        <span class="hint">원문(<code>**굵게**</code> 포함)이 그대로 들어갑니다 —
          위 박스는 렌더된 모습입니다.</span>
      <?php endif; ?>

      <form method="post" style="margin-top:16px">
        <input type="hidden" name="token" value="">
        <input type="hidden" name="qa_id" value="<?php echo (int)$q['qa_id'] ?>">

        <h2>답변 <span class="hint">— 승인하면 이 내용이 그대로 공개된다</span></h2>
        <textarea name="qa_answer" id="ansBox" rows="14"
          placeholder="해설을 인용해 짧고 정확하게. 질문자가 고른 보기가 왜 아닌지까지 짚으면 재질문이 줄어듭니다."><?php
          echo exf_h($q['qa_answer']) ?></textarea>

        <label class="chk" style="margin-top:9px">
          <input type="checkbox" name="qa_public" value="1" <?php echo (int)$q['qa_public'] ? 'checked' : '' ?>>
          공개 — 다른 이용자에게도 보인다 (과목게시판·문제 카드에 쌓인다)
        </label>
        <div class="hint">개인 사정이 섞인 질문은 체크를 풀어 비공개로 둡니다.
          공개된 답변은 다음 사람의 중복 질문을 막아 검수 부담을 줄입니다.</div>

        <div class="acts">
          <?php /* button[name=act] 로 어느 것을 눌렀는지 구분한다. adm/admin.js 가
                   submit 을 가로채 token 을 덮어쓰지만 name/value 는 건드리지 않는다. */ ?>
          <button type="submit" class="btn_b01" name="act" value="save">저장만</button>
          <button type="submit" class="btn_submit" name="act" value="approve"
                  onclick="return confirm('승인하면 이용자에게 공개됩니다.');">승인 · 공개</button>
          <?php if ($q['qa_status'] === 'approved' || $q['qa_status'] === 'rejected'): ?>
            <button type="submit" class="btn_b01 grow" name="act" value="reopen"
                    onclick="return confirm('대기 상태로 되돌립니다. 환불은 되돌리지 않습니다.');">대기로 되돌리기</button>
          <?php endif; ?>
        </div>
      </form>

      <?php if ($q['qa_status'] !== 'rejected'): ?>
      <form method="post" style="margin-top:18px;border-top:1px solid #eceff3;padding-top:14px">
        <input type="hidden" name="token" value="">
        <input type="hidden" name="qa_id" value="<?php echo (int)$q['qa_id'] ?>">
        <input type="hidden" name="act" value="reject">
        <h2>반려 <span class="hint">— 포인트를 환불한다</span></h2>
        <textarea name="reason" rows="3"
          placeholder="이용자에게 그대로 보입니다. 왜 답할 수 없는지 적어 주십시오."></textarea>
        <div class="acts">
          <button type="submit" class="btn_b01"
                  onclick="return confirm('반려하고 <?php echo number_format((int)$q['cost_units']) ?>원을 환불합니다.');">
            반려 · 환불</button>
          <span class="hint">
            <?php echo (int)$q['cost_units'] === 0
              ? '무료 질문이라 환불할 것이 없습니다.'
              : number_format((int)$q['cost_units']) . '원이 돌아갑니다. 원 지급분이 만료됐으면 30일짜리로 새로 발급됩니다.' ?>
          </span>
        </div>
      </form>
      <?php endif; ?>
    </div>

  </div>

<?php endif; ?>
</div>

<?php
require_once './admin.tail.php';
