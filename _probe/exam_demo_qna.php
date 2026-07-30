<?php
/**
 * exam_demo_qna.php — 과목게시판 예시 글(더미) 넣기 / 지우기.  ★ 캡처가 끝나면 삭제한다.
 *
 * 배치: /www/exam_demo_qna.php   (웹루트. common.php 와 같은 자리)
 * 접근: **최고관리자로 로그인한 상태**에서만 동작한다.
 *
 * 왜 화면으로 만드는가
 *   그누보드 게시판 글은 손으로 넣기 어렵다 — wr_num(정렬) · wr_parent · wr_is_comment ·
 *   부모의 wr_comment 카운트 · g5_board.bo_count_write 를 같이 맞춰야 하고,
 *   우리 쪽은 ex_qna 원장(bo_table · wr_id · sj_no · qa_status)까지 연결해야
 *   '답변완료' 배지와 질문 검수 화면이 함께 산다.
 *
 * ★★ 반드시 지운다 ★★
 *   이 글들은 **가상 답변**이다. 실서비스에 남으면 이용자가 진짜 답변으로 믿는다.
 *   그래서 넣은 글에 지울 표식을 박아두고(wr_10 = 'XAMPASS_DEMO') 한 버튼으로 되돌린다.
 *   표식은 basic 스킨이 화면에 쓰지 않는 여분 필드라 캡처에 찍히지 않는다.
 *
 * ⚠ 답변 내용은 **사실로 맞게** 썼다. 캡처는 마케팅에 쓰이고, 틀린 내용이 박히면
 *   신뢰를 잃는 쪽이 더 크다. 실제 SQLD 개념 기준으로 검토했다.
 */

include_once(__DIR__ . '/common.php');

header('Content-Type: text/html; charset=utf-8');

if (empty($member['mb_id'])) {
    exit('<meta charset="utf-8"><p style="font:14px sans-serif">'
       . '먼저 <a href="' . G5_BBS_URL . '/login.php">최고관리자로 로그인</a>한 뒤 다시 여십시오.</p>');
}
if ($is_admin !== 'super') {
    exit('<meta charset="utf-8"><p style="font:14px sans-serif">최고관리자만 실행할 수 있습니다.</p>');
}

const DEMO_MARK = 'XAMPASS_DEMO';   // wr_10 에 박는다. 지울 때 이걸로 찾는다

/** 문제집 → 게시판 테이블명. api/board.php · adm/exam_board_sync.php 와 같은 규칙. */
function exd_table($pd_id) {
    $t = preg_replace('/[^a-z0-9_]/', '_', strtolower((string)$pd_id));
    return substr($t . '_sj', 0, 20);
}
function h($s) { return htmlspecialchars((string)$s, ENT_QUOTES, 'UTF-8'); }

/* ── 예시 문답 ──────────────────────────────────────────────────────────────
 * sj  : 과목 번호(말머리를 이걸로 찾는다)
 * q   : 제목 — 이용자가 실제로 쓸 만한 말투. "무슨 과목 몇 번" 을 다 적기보다
 *       앞을 생략하는 쪽이 흔하다는 관찰을 반영했다.
 * body: 본문
 * a   : 관리자 답변 (댓글로 들어간다)
 */
$DEMO = array(
  array('sj'=>1, 'who'=>'수험생A',
    'q'=>'슈퍼타입/서브타입 변환에서 1:1 타입이랑 단일 테이블 차이가 헷갈려요',
    'body'=>"3회차 8번 문제인데요.\n\n슈퍼타입을 서브타입마다 나누는 게 1:1 타입이고, 다 합치는 게 단일 테이블(All in One)인 건 알겠는데\n실제 시험에서 어떤 걸 고르라는 건지 판단 기준이 안 잡힙니다.",
    'a'=>"판단 기준은 **서브타입별 속성 수와 접근 패턴** 두 개입니다.\n\n· 1:1 타입 — 서브타입마다 고유 속성이 많고, 각 서브타입을 따로 조회하는 경우\n· 단일 테이블 — 서브타입 고유 속성이 적고, 슈퍼타입 기준으로 전체를 자주 조회하는 경우\n· Plus 타입(슈퍼+서브 각각) — 그 중간\n\n시험에서는 보통 \"서브타입 속성이 많다 / 서브타입별로 조회한다\" 는 단서가 문제에 들어 있습니다. 그 단서를 찾으면 답이 정해집니다.\n\n단일 테이블의 대가는 **NULL 컬럼이 많아진다**는 것이고, 1:1 타입의 대가는 **조인이 늘어난다**는 것입니다. 이 트레이드오프를 물으면 그 관점으로 답하시면 됩니다."),

  array('sj'=>1, 'who'=>'김OO',
    'q'=>'정규화하면 성능이 무조건 좋아지는 거 아니었나요',
    'body'=>"정규화 문제에서 \"정규화는 조회 성능을 항상 향상시킨다\" 가 틀렸다고 나오는데\n중복이 줄면 당연히 빨라질 것 같은데 왜 틀린 건가요?",
    'a'=>"정규화는 **입력·수정·삭제 성능을 향상**시키고, **조회 성능은 나빠질 수 있습니다.**\n\n이유는 하나입니다 — 정규화하면 테이블이 쪼개지고, 원래 한 테이블에서 읽던 것을 **조인해서** 읽어야 합니다.\n\n· 중복 제거 → 갱신할 곳이 한 군데 → 입력/수정/삭제 유리\n· 테이블 분리 → 조인 증가 → 조회 불리할 수 있음\n\n그래서 조회가 압도적으로 많은 시스템에서는 일부러 **반정규화**를 합니다. 시험에서 \"항상\", \"무조건\" 이 들어간 보기는 대개 오답입니다."),

  array('sj'=>2, 'who'=>'박OO',
    'q'=>'NULL 비교는 왜 = 로 안 되나요',
    'body'=>"WHERE 컬럼 = NULL 로 쓰면 결과가 0건 나옵니다.\nIS NULL 을 써야 한다는 건 외웠는데 이유를 알고 싶습니다.",
    'a'=>"NULL 은 \"값이 없음\" 이 아니라 **\"값을 알 수 없음(unknown)\"** 입니다.\n\n알 수 없는 값과 무엇을 비교해도 결과는 참도 거짓도 아닌 **UNKNOWN** 이고, WHERE 절은 **참인 행만** 통과시킵니다. 그래서 0건이 나옵니다.\n\n```\nWHERE 컬럼 = NULL      → UNKNOWN → 통과 못 함\nWHERE 컬럼 <> NULL     → UNKNOWN → 통과 못 함 (이것도 안 됩니다)\nWHERE 컬럼 IS NULL     → TRUE/FALSE → 정상 동작\n```\n\n같은 이유로 `NULL + 100` 도 NULL 이고, `COUNT(컬럼)` 은 NULL 을 세지 않습니다(`COUNT(*)` 는 셉니다). 이 셋이 한 묶음으로 자주 나옵니다."),

  array('sj'=>2, 'who'=>'이OO',
    'q'=>'GROUP BY 없이 HAVING 쓸 수 있나요',
    'body'=>"기출에서 HAVING 만 있고 GROUP BY 가 없는 SQL 이 나왔는데 오류가 아니라고 하더라고요.\n이게 어떻게 되는 건가요?",
    'a'=>"됩니다. GROUP BY 가 없으면 **전체 행이 하나의 그룹**으로 취급되고, HAVING 은 그 한 그룹에 조건을 겁니다.\n\n```sql\nSELECT COUNT(*) FROM 주문 HAVING COUNT(*) > 100;\n```\n→ 전체 주문이 100건을 넘으면 건수를 반환하고, 아니면 **0건**을 반환합니다.\n\n구분해서 외우시면 좋습니다.\n· WHERE  — 그룹을 만들기 **전에** 행을 걸러낸다. 집계함수 못 씀\n· HAVING — 그룹을 만든 **후에** 그룹을 걸러낸다. 집계함수 씀\n\n실무에서 쓸 일은 드물지만 시험에는 \"오류가 발생한다\" 를 오답 보기로 자주 넣습니다."),

  array('sj'=>2, 'who'=>'최OO',
    'q'=>'ORDER BY 에 SELECT 에 없는 컬럼을 써도 되나요',
    'body'=>"SELECT 절에 없는 컬럼을 ORDER BY 에 쓰는 게 되는지 안 되는지 보기마다 다르게 나와서 혼란스럽습니다.",
    'a'=>"**일반 SELECT 는 되고, DISTINCT 나 집합 연산(UNION 등)이 붙으면 안 됩니다.**\n\n```sql\n-- 된다\nSELECT 상품명 FROM 상품 ORDER BY 등록일;\n\n-- 안 된다 (ORA-01791 등)\nSELECT DISTINCT 상품명 FROM 상품 ORDER BY 등록일;\nSELECT 상품명 FROM A UNION SELECT 상품명 FROM B ORDER BY 등록일;\n```\n\n이유는 **정렬 시점에 그 컬럼이 결과 집합에 남아 있는지**입니다. DISTINCT·UNION 은 중복을 제거하면서 SELECT 절에 없는 컬럼을 버리기 때문에 정렬 기준으로 쓸 수 없습니다.\n\nUNION 의 ORDER BY 는 마지막 SELECT 뒤에 **한 번만** 오고, 컬럼명 대신 **순번(1, 2 …)** 을 쓸 수 있다는 것도 같이 나옵니다."),
);

$msg = ''; $err = '';
$pd  = isset($_REQUEST['pd']) ? preg_replace('/[^a-z0-9\-]/', '', $_REQUEST['pd']) : '';

/* ── 실행 ──────────────────────────────────────────────────────────────── */
if ($_SERVER['REQUEST_METHOD'] === 'POST' && $pd !== '') {
    $act = isset($_POST['act']) ? $_POST['act'] : '';
    $bo  = exd_table($pd);
    $boq = sql_real_escape_string($bo);
    $wt  = $g5['write_prefix'] . $bo;

    $board = sql_fetch("select bo_table, bo_category_list from " . $g5['board_table'] . "
                         where bo_table = '$boq'");
    if (!$board) {
        $err = '게시판 ' . $bo . ' 이 없습니다. 먼저 만들고 말머리를 맞추십시오.';
    }
    elseif ($act === 'clear') {
        /* 표식이 박힌 글과 그 댓글, 연결된 ex_qna 를 지운다.
         * 댓글은 wr_parent 로 딸려 있으므로 부모 목록을 먼저 뽑는다. */
        $ids = array();
        $res = sql_query("select wr_id from $wt where wr_10 = '" . DEMO_MARK . "' and wr_is_comment = 0", false);
        while ($res && $r = sql_fetch_array($res)) $ids[] = (int)$r['wr_id'];

        if (!$ids) {
            $err = '지울 예시 글이 없습니다.';
        } else {
            $in = implode(',', $ids);
            sql_query("delete from $wt where wr_parent in ($in)", false);   // 본문 + 댓글
            sql_query("delete from ex_qna where bo_table = '$boq' and wr_id in ($in)", false);
            sql_query("update " . $g5['board_table'] . "
                          set bo_count_write = (select count(*) from $wt where wr_is_comment = 0),
                              bo_count_comment = (select count(*) from $wt where wr_is_comment = 1)
                        where bo_table = '$boq'", false);
            $msg = '예시 글 ' . count($ids) . '건과 딸린 댓글·원장을 지웠습니다.';
        }
    }
    elseif ($act === 'seed') {
        /* 말머리 목록 — 과목 번호로 찾기 위해 ex_problem 을 본다.
         * 게시판 말머리는 exam_board_sync.php 가 과목명으로 맞춰뒀다. */
        $cats = array();
        $res = sql_query("select distinct sj_no, sj_name from ex_problem
                           where pd_id = '" . sql_real_escape_string($pd) . "'
                             and pr_open = 1 and sj_name <> '' order by sj_no", false);
        while ($res && $r = sql_fetch_array($res)) $cats[(int)$r['sj_no']] = $r['sj_name'];

        if (!$cats) {
            $err = $pd . ' 에 노출 중인 문제가 없어 과목(말머리)을 뽑을 수 없습니다.';
        } else {
            $dup = sql_fetch("select wr_id from $wt where wr_10 = '" . DEMO_MARK . "' limit 1");
            if ($dup) {
                $err = '이미 예시 글이 있습니다. 먼저 [예시 글 지우기] 를 누르십시오.';
            } else {
                $n = 0;
                $ip = sql_real_escape_string(substr($_SERVER['REMOTE_ADDR'], 0, 45));
                // 최근 글이 위로 오도록 과거 시각부터 배치한다. 하루에 하나씩 뒤로.
                $base = G5_SERVER_TIME - (count($DEMO) + 1) * 86400;

                foreach ($DEMO as $i => $d) {
                    $ca = isset($cats[$d['sj']]) ? $cats[$d['sj']] : '기타';
                    $dt = date('Y-m-d H:i:s', $base + $i * 86400 + 3600 * (9 + $i % 7));

                    /* ── 질문 글 ────────────────────────────────────────────
                     * wr_num 은 정렬 키다. 그누보드는 min(wr_num)-1 을 쓴다 —
                     * 값이 작을수록 위로 온다. 우리는 -wr_id 로 두면 최신이 위로 온다. */
                    sql_query("insert into $wt
                        (wr_num, wr_reply, wr_parent, wr_is_comment, wr_comment, wr_comment_reply,
                         ca_name, wr_option, wr_subject, wr_content, wr_seo_title,
                         wr_link1, wr_link2, wr_link1_hit, wr_link2_hit,
                         wr_hit, wr_good, wr_nogood, mb_id, wr_password, wr_name, wr_email,
                         wr_homepage, wr_datetime, wr_file, wr_last, wr_ip, wr_10)
                      values
                        (0, '', 0, 0, 1, '',
                         '" . sql_real_escape_string($ca) . "', '',
                         '" . sql_real_escape_string($d['q']) . "',
                         '" . sql_real_escape_string($d['body']) . "', '',
                         '', '', 0, 0,
                         " . (17 + $i * 13) . ", 0, 0, '', '', '" . sql_real_escape_string($d['who']) . "', '',
                         '', '" . sql_real_escape_string($dt) . "', 0,
                         '" . sql_real_escape_string($dt) . "', '$ip', '" . DEMO_MARK . "')", false);

                    $wr_id = (int)sql_insert_id();
                    if (!$wr_id) continue;

                    sql_query("update $wt set wr_num = " . (-$wr_id) . ", wr_parent = $wr_id
                                where wr_id = $wr_id", false);

                    /* ── 관리자 답변 (댓글) ─────────────────────────────────
                     * 왜 댓글인가: 답변글(wr_reply)로 넣으면 목록에 별도 행으로 떠서
                     * "질문 5개" 가 "10개" 로 보인다. Q&A 는 한 줄에 [1] 로 보이는 게 맞다. */
                    $adt = date('Y-m-d H:i:s', strtotime($dt) + 3600 * 5);
                    sql_query("insert into $wt
                        (wr_num, wr_reply, wr_parent, wr_is_comment, wr_comment, wr_comment_reply,
                         ca_name, wr_option, wr_subject, wr_content, wr_seo_title,
                         wr_link1, wr_link2, wr_link1_hit, wr_link2_hit,
                         wr_hit, wr_good, wr_nogood, mb_id, wr_password, wr_name, wr_email,
                         wr_homepage, wr_datetime, wr_file, wr_last, wr_ip, wr_10)
                      values
                        (" . (-$wr_id) . ", '', $wr_id, 1, 0, '',
                         '', '', '', '" . sql_real_escape_string($d['a']) . "', '',
                         '', '', 0, 0,
                         0, 0, 0, '" . sql_real_escape_string($member['mb_id']) . "', '',
                         '" . sql_real_escape_string($member['mb_nick']) . "', '',
                         '', '" . sql_real_escape_string($adt) . "', 0,
                         '', '$ip', '" . DEMO_MARK . "')", false);

                    /* ── 원장(ex_qna) ───────────────────────────────────────
                     * 이게 있어야 목록에 '답변완료' 배지가 뜬다 —
                     * api/board.php 는 댓글 수가 아니라 qa_status='approved' 로 판정한다.
                     * 검수 화면(adm/exam_qna_list.php)에도 '완료' 로 함께 나타난다. */
                    sql_query("insert into ex_qna
                        (qa_parent, mb_id, pd_id, kind, pr_key, sj_no, bo_table, wr_id,
                         qa_question, qa_chosen, qa_status, qa_answer,
                         cost_units, qa_credit_ok, qa_public, qa_answered_at, created_at, edited_by)
                      values
                        (0, '" . sql_real_escape_string($member['mb_id']) . "',
                         '" . sql_real_escape_string($pd) . "', 'qna', '', " . (int)$d['sj'] . ",
                         '$boq', $wr_id,
                         '" . sql_real_escape_string($d['q']) . "', -1, 'approved',
                         '" . sql_real_escape_string($d['a']) . "',
                         0, 1, 1, '" . sql_real_escape_string($adt) . "',
                         '" . sql_real_escape_string($dt) . "',
                         '" . sql_real_escape_string($member['mb_id']) . "')", false);
                    $n++;
                }

                sql_query("update " . $g5['board_table'] . "
                              set bo_count_write = (select count(*) from $wt where wr_is_comment = 0),
                                  bo_count_comment = (select count(*) from $wt where wr_is_comment = 1)
                            where bo_table = '$boq'", false);

                $msg = '예시 문답 ' . $n . '건을 넣었습니다. 각 글에 관리자 답변(댓글)과 원장이 함께 들어갔습니다.';
            }
        }
    }
}

/* ── 현황 ──────────────────────────────────────────────────────────────── */
$rows = array();
$res = sql_query("select pd_id, pd_name from ex_product order by pd_sort, pd_id", false);
while ($res && $r = sql_fetch_array($res)) {
    $bo = exd_table($r['pd_id']);
    $boq = sql_real_escape_string($bo);
    $b = sql_fetch("select bo_table, bo_category_list from " . $g5['board_table'] . " where bo_table = '$boq'");
    $total = $demo = 0;
    if ($b) {
        $t = sql_fetch("select count(*) as c from " . $g5['write_prefix'] . $bo . " where wr_is_comment = 0");
        $d = sql_fetch("select count(*) as c from " . $g5['write_prefix'] . $bo . "
                         where wr_is_comment = 0 and wr_10 = '" . DEMO_MARK . "'");
        $total = $t ? (int)$t['c'] : 0;
        $demo  = $d ? (int)$d['c'] : 0;
    }
    $rows[] = array('pd_id'=>$r['pd_id'], 'pd_name'=>$r['pd_name'], 'bo'=>$bo,
                    'board'=>$b, 'total'=>$total, 'demo'=>$demo);
}
?>
<!doctype html><meta charset="utf-8"><title>과목게시판 예시 글</title>
<style>
 body{font:14px/1.7 -apple-system,"Malgun Gothic",sans-serif;max-width:980px;margin:2rem auto;padding:0 1rem;color:#222}
 h1{font-size:1.3rem} h2{font-size:1rem;margin:1.8rem 0 .6rem;border-bottom:1px solid #ddd;padding-bottom:5px}
 table{border-collapse:collapse;width:100%;margin:.6rem 0;font-size:13.5px}
 td,th{border:1px solid #dde1e8;padding:8px 11px;text-align:left}
 th{background:#f7f8fa}
 code{background:#f4f5f7;padding:1px 5px;border-radius:3px;font-family:Consolas,monospace}
 .warn{background:#fff6e5;border:1px solid #d9901a;padding:.8rem 1rem;margin:1rem 0;border-radius:6px}
 .err{background:#fdeced;border:1px solid #c22638;padding:.8rem 1rem;margin:1rem 0;border-radius:6px}
 .good{background:#e9f7ef;border:1px solid #0a7f3f;padding:.8rem 1rem;margin:1rem 0;border-radius:6px}
 .btn{display:inline-block;padding:.45rem 1rem;border-radius:5px;border:0;cursor:pointer;font:inherit;font-weight:700}
 .btn.p{background:#1f4fd8;color:#fff} .btn.d{background:#fff;color:#c22638;border:1px solid #c22638}
 .dim{color:#888} .ok{color:#0a7f3f;font-weight:700} .no{color:#c22638;font-weight:700}
 details{margin:.5rem 0} summary{cursor:pointer;font-weight:700}
 pre{background:#f7f8fa;border:1px solid #e6eaf2;border-radius:6px;padding:10px 12px;overflow-x:auto;
   font-size:12.5px;line-height:1.65;white-space:pre-wrap}
</style>

<h1>과목게시판 예시 글 <span class="dim">— 캡처가 끝나면 이 파일을 삭제</span></h1>

<div class="warn">
  <b>이 글들은 가상 답변입니다.</b> 실서비스에 남으면 이용자가 진짜 답변으로 믿습니다.<br>
  넣은 글에 표식(<code>wr_10 = XAMPASS_DEMO</code>)을 박아두므로 <b>[예시 글 지우기]</b> 로 한 번에 되돌립니다.
  표식은 화면에 쓰이지 않는 여분 필드라 <b>캡처에 찍히지 않습니다.</b><br>
  <b>정식 오픈 전에 반드시 지우십시오.</b>
</div>

<?php if ($msg): ?><div class="good"><?php echo h($msg) ?></div><?php endif; ?>
<?php if ($err): ?><div class="err"><?php echo h($err) ?></div><?php endif; ?>

<h2>문제집별 현황</h2>
<table>
  <tr><th>문제집</th><th>게시판</th><th>전체 글</th><th>예시 글</th><th>작업</th></tr>
  <?php foreach ($rows as $x): ?>
  <tr>
    <td><?php echo h($x['pd_name']) ?><br><code><?php echo h($x['pd_id']) ?></code></td>
    <td><code><?php echo h($x['bo']) ?></code>
      <?php if ($x['board']): ?>
        <br><a href="<?php echo G5_BBS_URL ?>/board.php?bo_table=<?php echo h($x['bo']) ?>" target="_blank">열기</a>
      <?php else: ?>
        <br><span class="no">없음</span>
      <?php endif; ?>
    </td>
    <td><?php echo $x['board'] ? number_format($x['total']) : '—' ?></td>
    <td class="<?php echo $x['demo'] ? 'ok' : 'dim' ?>"><?php echo $x['board'] ? number_format($x['demo']) : '—' ?></td>
    <td>
      <?php if (!$x['board']): ?>
        <span class="dim">게시판을 먼저 만드십시오</span>
      <?php elseif ($x['demo']): ?>
        <form method="post" style="margin:0" onsubmit="return confirm('예시 글과 댓글·원장을 지웁니다.');">
          <input type="hidden" name="pd" value="<?php echo h($x['pd_id']) ?>">
          <input type="hidden" name="act" value="clear">
          <button class="btn d">예시 글 지우기</button>
        </form>
      <?php else: ?>
        <form method="post" style="margin:0">
          <input type="hidden" name="pd" value="<?php echo h($x['pd_id']) ?>">
          <input type="hidden" name="act" value="seed">
          <button class="btn p">예시 글 <?php echo count($DEMO) ?>건 넣기</button>
        </form>
      <?php endif; ?>
    </td>
  </tr>
  <?php endforeach; ?>
</table>

<h2>무엇이 들어가는가</h2>
<p>질문 <?php echo count($DEMO) ?>건 + 각 글에 <b>관리자 답변(댓글)</b> + <b>원장 <code>ex_qna</code> 1행</b>.</p>
<ul>
  <li>말머리는 <code>ex_problem</code> 의 과목명으로 붙습니다 — 과목 칩 필터가 실제로 동작합니다.</li>
  <li>답변을 <b>답변글이 아니라 댓글</b>로 넣습니다. 답변글이면 목록에 별도 행이 생겨 "질문 5개"가 "10개"로 보입니다.</li>
  <li><code>ex_qna.qa_status = 'approved'</code> 를 넣으므로 목록에 <b>답변완료</b> 배지가 뜨고,
      <a href="<?php echo G5_ADMIN_URL ?>/exam_qna_list.php">질문 검수</a> 화면에도 '완료'로 나타납니다.</li>
  <li>등록일을 하루씩 벌려 넣습니다 — 같은 시각이면 목록이 어색합니다.</li>
  <li>조회수도 조금씩 다르게 넣습니다.</li>
</ul>

<details>
  <summary>들어가는 문답 미리보기</summary>
  <?php foreach ($DEMO as $d): ?>
    <pre><b>[<?php echo (int)$d['sj'] ?>과목] <?php echo h($d['q']) ?></b>  — <?php echo h($d['who']) ?>

<?php echo h($d['body']) ?>

<b>▸ 답변</b>
<?php echo h($d['a']) ?></pre>
  <?php endforeach; ?>
</details>

<div class="warn">
  캡처가 끝나면 <b>① [예시 글 지우기]</b> → <b>② <code>/www/exam_demo_qna.php</code> 삭제</b> 순서로 정리합니다.<br>
  <span class="dim">파일을 먼저 지우면 되돌릴 화면이 없어집니다. 그때는 DB 에서
  <code>wr_10 = 'XAMPASS_DEMO'</code> 로 직접 지워야 합니다.</span>
</div>
