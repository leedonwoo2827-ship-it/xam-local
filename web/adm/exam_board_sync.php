<?php
/**
 * 과목게시판 점검 · 말머리 동기화.
 *
 * 과목게시판은 **문제집당 1개**이고 과목은 말머리(bo_category_list)로 구분한다.
 * 게시판 생성 자체는 운영자가 그누보드 기본 화면(게시판 관리 → 추가)에서 한다 —
 * g5_board 는 컬럼이 90개 넘고 권한·스킨·업로드 정책이 다 거기 있어서
 * 우리가 흉내내면 반드시 어딘가 빠진다.
 *
 * 이 화면이 하는 일은 하나다: **말머리를 ex_problem 의 과목 목록과 맞춘다.**
 * 왜 이것만 자동화하는가 — 과목명 오타 하나로 api/board.php 의 말머리 필터가
 * 조용히 빈 목록을 돌려준다. 에러가 안 나서 사람이 못 잡는 종류의 고장이다.
 *
 * bo_table 규칙 (api/board.php 의 ex_board_table() 과 같아야 한다):
 *   sqld    → sqld_sj
 *   bdae-w  → bdae_w_sj      (하이픈은 _ 로. bo_table 은 영문·숫자·_ 20자)
 */
$sub_menu = '600200';
require_once './_common.php';

auth_check_menu($auth, $sub_menu, 'r');

/** 문제집 → 게시판 테이블명. api/board.php 와 같은 규칙이다. */
function exb_table($pd_id) {
    $t = preg_replace('/[^a-z0-9_]/', '_', strtolower((string)$pd_id));
    return substr($t . '_sj', 0, 20);
}

$msg = ''; $err = '';

/* ── 동기화 ────────────────────────────────────────────────────────────── */
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    auth_check_menu($auth, $sub_menu, 'w');
    if (function_exists('check_admin_token')) check_admin_token();
    else                                     check_token();

    $pd = isset($_POST['pd_id']) ? preg_replace('/[^a-z0-9\-]/', '', $_POST['pd_id']) : '';
    $bo = exb_table($pd);

    $b = sql_fetch("select bo_table from " . $g5['board_table'] . "
                     where bo_table = '" . sql_real_escape_string($bo) . "'");
    if (!$b) {
        $err = '게시판 ' . $bo . ' 이 없습니다. 먼저 게시판을 만드십시오.';
    } else {
        $subs = array();
        $res = sql_query("select distinct sj_no, sj_name from ex_problem
                           where pd_id = '" . sql_real_escape_string($pd) . "'
                             and pr_open = 1 and sj_name <> ''
                           order by sj_no", false);
        while ($res && $r = sql_fetch_array($res)) $subs[] = $r['sj_name'];

        if (!$subs) {
            $err = $pd . ' 에 노출 중인 문제가 없어 과목을 뽑을 수 없습니다. 문제 임포트를 먼저 하십시오.';
        } else {
            /* 말머리에 '기타' 를 붙인다. 과목이 애매한 질문(시험 접수·학습법 등)이
             * 반드시 들어오는데, 받을 말머리가 없으면 이용자가 아무 과목이나 고른다.
             * 그러면 과목별 필터의 신뢰도가 떨어진다. */
            $list = implode('|', array_merge($subs, array('기타')));

            sql_query("update " . $g5['board_table'] . "
                          set bo_use_category = 1,
                              bo_category_list = '" . sql_real_escape_string($list) . "'
                        where bo_table = '" . sql_real_escape_string($bo) . "'", false);
            $msg = $bo . ' 말머리를 ' . count($subs) . '과목 + 기타 로 맞췄습니다: ' . $list;
        }
    }
}

/* ── 현황 ──────────────────────────────────────────────────────────────── */
$rows = array();
$res = sql_query("select pd_id, pd_name, pd_open, pd_sort from ex_product order by pd_sort, pd_id", false);
while ($res && $r = sql_fetch_array($res)) {
    $pd = $r['pd_id'];
    $bo = exb_table($pd);
    $boq = sql_real_escape_string($bo);

    $b = sql_fetch("select bo_table, bo_subject, bo_use_category, bo_category_list
                      from " . $g5['board_table'] . " where bo_table = '$boq'");

    $subs = array();
    $r2 = sql_query("select distinct sj_no, sj_name from ex_problem
                      where pd_id = '" . sql_real_escape_string($pd) . "'
                        and pr_open = 1 and sj_name <> ''
                      order by sj_no", false);
    while ($r2 && $x = sql_fetch_array($r2)) $subs[] = $x['sj_name'];

    $cats = array();
    if ($b && $b['bo_category_list'] !== '') {
        foreach (explode('|', $b['bo_category_list']) as $c) {
            $c = trim($c);
            if ($c !== '') $cats[] = $c;
        }
    }

    // 기대 말머리 = 과목 + 기타
    $want = $subs ? array_merge($subs, array('기타')) : array();
    $posts = 0;
    if ($b) {
        $p = sql_fetch("select count(*) as c from " . $g5['write_prefix'] . $bo . " where wr_is_comment = 0");
        $posts = $p ? (int)$p['c'] : 0;
    }

    $rows[] = array(
        'pd_id' => $pd, 'pd_name' => $r['pd_name'], 'pd_open' => (int)$r['pd_open'],
        'bo' => $bo, 'board' => $b, 'subs' => $subs, 'cats' => $cats,
        'want' => $want, 'posts' => $posts,
        'ok' => ($b && $want && $cats === $want && (int)$b['bo_use_category'] === 1),
    );
}

$g5['title'] = '과목게시판';
require_once './admin.head.php';

function exb_h($s) { return htmlspecialchars((string)$s, ENT_QUOTES, 'UTF-8'); }
?>

<style>
.exb{max-width:1100px}
.exb .box{background:#fff;border:1px solid #e3e6ec;border-radius:8px;padding:18px 20px;margin:0 0 16px}
.exb h2{font-size:15px;margin:0 0 12px;font-weight:700}
.exb .msg{padding:11px 16px;border-radius:6px;margin:0 0 14px;font-size:14px;line-height:1.6}
.exb .msg.err{background:#fdeced;border:1px solid #c22638;color:#8c1220}
.exb .msg.good{background:#e9f7ef;border:1px solid #0a7f3f;color:#075c2d}
.exb table{border-collapse:collapse;width:100%;font-size:13px}
.exb th,.exb td{border:1px solid #e3e6ec;padding:8px 10px;text-align:left;vertical-align:top}
.exb th{background:#f7f8fa;font-weight:600;white-space:nowrap}
.exb code{background:#f4f5f7;padding:1px 5px;border-radius:3px;font-family:Consolas,monospace}
.exb .pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:700}
.exb .pill.ok{background:#e9f7ef;color:#075c2d}
.exb .pill.no{background:#fdeced;color:#8c1220}
.exb .pill.wait{background:#fff6e5;color:#8a5a00}
.exb .hint{color:#666;font-size:13px;line-height:1.75}
.exb .cats{font-size:12.5px;color:#555;line-height:1.7}
.exb .cats b{color:#0a7f3f}
.exb ol{margin:8px 0 0 20px;font-size:13px;line-height:1.9}
.exb .btn_submit{padding:5px 12px;font-size:12.5px}
</style>

<div class="exb">

<?php if ($msg): ?><div class="msg good"><?php echo exb_h($msg) ?></div><?php endif; ?>
<?php if ($err): ?><div class="msg err"><?php echo exb_h($err) ?></div><?php endif; ?>

  <div class="box">
    <h2>문제집별 과목게시판</h2>
    <table>
      <tr><th>문제집</th><th>게시판</th><th>상태</th><th>말머리</th><th>글</th><th>동기화</th></tr>
      <?php foreach ($rows as $x): ?>
      <tr>
        <td><?php echo exb_h($x['pd_name']) ?><br><code><?php echo exb_h($x['pd_id']) ?></code></td>
        <td><code><?php echo exb_h($x['bo']) ?></code>
          <?php if ($x['board']): ?>
            <br><a href="<?php echo G5_BBS_URL ?>/board.php?bo_table=<?php echo exb_h($x['bo']) ?>" target="_blank">열기</a>
            · <a href="./board_form.php?w=u&amp;bo_table=<?php echo exb_h($x['bo']) ?>">설정</a>
          <?php endif; ?>
        </td>
        <td>
          <?php if (!$x['board']): ?>
            <span class="pill no">없음</span>
          <?php elseif (!$x['subs']): ?>
            <span class="pill wait">문제 0건</span>
          <?php elseif ($x['ok']): ?>
            <span class="pill ok">정상</span>
          <?php else: ?>
            <span class="pill no">말머리 불일치</span>
          <?php endif; ?>
        </td>
        <td class="cats">
          <?php if ($x['want']): ?>
            기대: <b><?php echo exb_h(implode(' | ', $x['want'])) ?></b><br>
          <?php else: ?>
            기대: <span class="hint">(문제를 임포트해야 과목이 나옵니다)</span><br>
          <?php endif; ?>
          현재: <?php echo $x['cats'] ? exb_h(implode(' | ', $x['cats'])) : '<span class="hint">(없음)</span>' ?>
        </td>
        <td><?php echo $x['board'] ? number_format($x['posts']) : '—' ?></td>
        <td>
          <?php if ($x['board'] && $x['subs']): ?>
          <form method="post" style="margin:0">
            <input type="hidden" name="token" value="">
            <input type="hidden" name="pd_id" value="<?php echo exb_h($x['pd_id']) ?>">
            <input type="submit" class="btn_submit" value="말머리 맞추기">
          </form>
          <?php else: ?>
            <span class="hint">—</span>
          <?php endif; ?>
        </td>
      </tr>
      <?php endforeach; ?>
    </table>
  </div>

  <div class="box">
    <h2>게시판 만드는 절차 <span class="hint">— 문제집을 추가할 때 1회</span></h2>
    <div class="hint">
      게시판 생성은 자동화하지 않습니다. <code>g5_board</code> 는 컬럼이 90개가 넘고
      권한·스킨·업로드 정책이 모두 거기 있어서, 우리가 만들면 반드시 어딘가 빠집니다.
      대신 <b>말머리만</b> 위 버튼으로 맞춥니다 — 과목명 오타 하나로 필터가 조용히
      빈 목록을 돌려주는 것이 사람이 잡기 가장 어려운 고장입니다.
    </div>
    <ol>
      <li><a href="./board_list.php">게시판 관리</a> → <b>게시판 추가</b></li>
      <li>테이블명(<code>bo_table</code>)을 위 표의 <b>게시판</b> 열에 적힌 값 그대로 넣습니다.
        <span class="hint">이름이 다르면 과목게시판 탭이 게시판을 못 찾습니다.</span></li>
      <li>제목은 <code>◯◯ 과목게시판</code> 처럼. 그룹·스킨은 공지 게시판과 같게 두면 됩니다.</li>
      <li>글쓰기·읽기 권한을 정합니다.
        <span class="hint">읽기는 비회원까지 열어두는 것을 권합니다 — 쌓인 공개 Q&amp;A 가
        신규 방문자에게 보여야 수강 신청으로 이어집니다.</span></li>
      <li>저장한 뒤 이 화면에서 <b>말머리 맞추기</b>를 누릅니다.</li>
    </ol>
  </div>

  <div class="box">
    <h2>동작</h2>
    <div class="hint">
      <b>말머리 = 과목 + 기타.</b> <code>ex_problem</code> 의 <code>sj_name</code> 을
      <code>sj_no</code> 순서로 뽑아 <code>bo_category_list</code> 에 넣습니다.
      <b>기타</b>를 붙이는 이유: 과목이 애매한 질문(접수·학습법)이 반드시 들어오는데
      받을 말머리가 없으면 이용자가 아무 과목이나 골라서 과목 필터의 신뢰도가 떨어집니다.<br><br>

      <b>이용자 화면</b> — <code>/exam/check.php?pd=◯◯&amp;m=board</code> 의 넷째 탭입니다.
      과목 칩을 목록보다 먼저 보여주고, 전체 보기·질문하기는 게시판으로(새 창) 넘깁니다.
      문제 화면에서 질문하면 과목·회차·문항이 자동으로 채워집니다.<br><br>

      <b>답변완료 판정</b>은 게시판 댓글 수가 아니라 <code>ex_qna.qa_status = 'approved'</code> 입니다.
      회원끼리 주고받은 댓글을 답변으로 셀 수 없습니다. 관리자가 확정한 것만 완료입니다.<br><br>

      ⚠ <b>말머리를 손으로 고치지 마십시오.</b> 과목명과 한 글자라도 다르면
      그 과목 필터가 빈 목록이 되고 에러는 나지 않습니다. 과목이 바뀌면(재임포트 후)
      이 화면에서 다시 맞춥니다.
    </div>
  </div>

</div>

<?php
require_once './admin.tail.php';
