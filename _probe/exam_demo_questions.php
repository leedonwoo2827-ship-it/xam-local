<?php
/**
 * exam_demo_questions.php — 검수·초안 테스트용 더미 질문 넣기 / 지우기.
 *                            ★ 확인이 끝나면 파일을 삭제한다.
 *
 * 배치: /www/exam_demo_questions.php   (웹루트. common.php 와 같은 자리)
 * 접근: 최고관리자로 로그인한 상태에서만 동작한다.
 *
 * ── 왜 필요한가 ────────────────────────────────────────────────────────────
 * 질문 검수 화면과 LLM 초안 생성을 확인하려면 질문이 있어야 하는데, 실제 회원 질문을
 * 기다릴 수 없다. 손으로 넣으려면 `ex_qna` 의 20개 컬럼(상태·차감·과목·문제키)을
 * 전부 맞춰야 하고, 하나라도 틀리면 검수 화면에서 다른 증상으로 나타난다.
 *
 * ── 실제 등록과 같은 값으로 넣는다 ─────────────────────────────────────────
 * `api/qna.php` 가 무료 기간(`pd_config.charge` 미설정)에 쓰는 값과 **똑같이** 넣는다:
 *   `cost_units = 0` · `qa_credit_ok = 1` · `qa_status = 'pending'` · `qa_public = 1`
 * 다르게 넣으면 검수 화면에 '차감 미확정' 경고가 10개 뜨고, 그게 버그인지
 * 더미 탓인지 구분할 수 없게 된다.
 *
 * ── 질문 문구를 문제의 태그에서 만든다 ─────────────────────────────────────
 * `ex_problem.tags_json` 에 개념이 들어 있어서("ERD", "식별 관계") 그걸 끼워 넣으면
 * 질문이 그 문제에 대한 것처럼 읽힌다. **초안 품질 테스트에는 이게 중요하다** —
 * "이 문제 모르겠어요" 같은 빈 질문으로는 프롬프트가 제대로 도는지 알 수 없다.
 *
 * ★★ 반드시 지운다 ★★
 *   가상 질문이다. `bo_table = '_demo'` 표식을 박아두고 한 버튼으로 되돌린다.
 *   (게시판 이름에 밑줄로 시작하는 값은 쓰지 않으므로 실제 질문과 섞이지 않는다.
 *    `wr_id = 0` 이라 검수 화면의 게시판 링크도 뜨지 않는다.)
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

const DQ_MARK = '_demo';      // ex_qna.bo_table 에 박는다. 지울 때 이걸로 찾는다
const DQ_N    = 10;

$mb_id = isset($_REQUEST['mb']) ? preg_replace('/[^0-9a-z_]/i', '', $_REQUEST['mb']) : 'guest5';
$pd_id = isset($_REQUEST['pd']) ? preg_replace('/[^0-9a-z\-]/i', '', $_REQUEST['pd']) : 'sqld';

$msg = ''; $err = ''; $rows_made = array();

/* 질문 템플릿 — {c} 는 질문자가 고른 보기, {t} 는 문제의 개념 태그.
 * 실제 수험생이 쓰는 결로 썼다: 대개 '내가 고른 게 왜 틀렸나' 를 묻는다. */
$T_QNA = array(
    '{c}번을 골랐는데 틀렸습니다. {t} 개념이 헷갈리는데 왜 답이 아닌지 알려주세요.',
    '해설을 읽어도 {t} 부분이 이해가 안 됩니다. {c}번과 정답의 차이를 짚어주실 수 있나요?',
    '{t} 를 이렇게 이해했는데 맞나요? 그래서 {c}번이라고 봤습니다.',
    '{c}번이 왜 안 되는지 모르겠습니다. {t} 에서 예외가 있는 건가요?',
    '{t} 관련 문제는 계속 틀립니다. 어떤 기준으로 판단해야 하는지 정리해주세요.',
    '{c}번도 맞는 설명처럼 보이는데 왜 정답이 아닌가요? {t} 조건이 다른 건가요?',
    '{t} 는 실무에서도 이렇게 쓰나요? 시험에서만 이렇게 나오는 건지 궁금합니다.',
    '보기 {c}번과 정답이 거의 같아 보입니다. {t} 에서 둘을 가르는 게 무엇인가요?',
);
$T_REPORT = array(
    '{c}번도 정답이 될 수 있을 것 같습니다. {t} 기준으로 보면 두 개가 다 맞지 않나요? 확인 부탁드립니다.',
    '정답이 잘못된 것 같습니다. {t} 로 판단하면 {c}번이 맞는 것으로 보입니다.',
);

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    check_token();
    $act = isset($_POST['act']) ? $_POST['act'] : '';

    if ($act === 'del') {
        /* 초안까지 지운다 — 표식이 있는 행만 대상이므로 실제 질문은 건드리지 않는다 */
        $r = sql_fetch("select count(*) as c from ex_qna where bo_table = '" . DQ_MARK . "'");
        sql_query("delete from ex_qna where bo_table = '" . DQ_MARK . "'", false);
        // 감사 로그의 draft 기록은 남긴다 — 원가를 얼마 썼는지는 지우면 안 된다
        $msg = '더미 질문 ' . (int)$r['c'] . '건을 지웠습니다. (원가 로그는 남겨둡니다)';

    } elseif ($act === 'ins') {
        // 회원 실재 확인 — 없는 mb_id 로 넣으면 검수 화면에서 닉이 빈칸으로 나온다
        $m = sql_fetch("select mb_id, mb_nick from {$g5['member_table']}
                         where mb_id = '" . sql_real_escape_string($mb_id) . "'");
        if (!$m) {
            $err = "회원 '{$mb_id}' 가 없습니다. 아이디를 확인하십시오.";
        } else {
            $prod = sql_fetch("select pd_id, pd_name from ex_product
                                where pd_id = '" . sql_real_escape_string($pd_id) . "'");
            if (!$prod) {
                $err = "문제집 '{$pd_id}' 가 없습니다.";
            } else {
                /* 과목이 골고루 섞이게 뽑는다. 한 과목에 몰리면 과목 필터를 확인할 수 없다.
                   태그가 있는 문제를 우선한다 — 질문 문구를 태그로 만들기 때문이다. */
                $probs = array();
                $res = sql_query("select pr_key, pr_no, rd_no, sj_no, sj_name, tags_json,
                                         choices_json, answer_index
                                    from ex_problem
                                   where pd_id = '" . sql_real_escape_string($pd_id) . "'
                                     and pr_open = 1
                                     and tags_json is not null and tags_json <> '[]'
                                   order by sj_no, rd_no, pr_no", false);
                while ($res && $r = sql_fetch_array($res)) $probs[] = $r;

                if (count($probs) < DQ_N) {
                    $err = '문제가 부족합니다(' . count($probs) . '건). 먼저 문제를 임포트하십시오.';
                } else {
                    /* 고르게 퍼뜨린다 — 앞에서 10개 연속으로 집으면 1과목만 나온다 */
                    $step = (int)floor(count($probs) / DQ_N);
                    if ($step < 1) $step = 1;
                    $pick = array();
                    for ($i = 0; count($pick) < DQ_N && $i < count($probs); $i += $step) $pick[] = $probs[$i];

                    $n_qna = 0; $n_rep = 0;
                    foreach ($pick as $i => $p) {
                        $tags = json_decode((string)$p['tags_json'], true);
                        $tag  = (is_array($tags) && $tags) ? $tags[0] : $p['sj_name'];

                        /* 오답 하나를 결정적으로 고른다 — 정답을 고르고 '왜 틀렸나' 하면 이상하다 */
                        $ch = json_decode((string)$p['choices_json'], true);
                        $n  = (is_array($ch) && $ch) ? count($ch) : 4;
                        $ans = ($p['answer_index'] === null) ? -1 : (int)$p['answer_index'];
                        $chosen = ($ans >= 0) ? (($ans + 1 + ($i % max(1, $n - 1))) % $n) : 0;
                        $circ = array('①','②','③','④','⑤');
                        $cl = isset($circ[$chosen]) ? $circ[$chosen] : (string)($chosen + 1);

                        // 8건은 질문, 2건은 오류 신고 — 두 종류가 다 보여야 kind 필터를 확인할 수 있다
                        $is_rep = ($i % 5 === 4);
                        if ($is_rep) { $tpl = $T_REPORT[$n_rep % count($T_REPORT)]; $n_rep++; }
                        else         { $tpl = $T_QNA[$n_qna % count($T_QNA)];       $n_qna++; }
                        $q_text = str_replace(array('{c}', '{t}'), array($cl, $tag), $tpl);

                        /* created_at 을 계단식으로 과거로 밀어둔다 — 검수 화면 정렬이
                           '오래 기다린 순' 이라 전부 같은 시각이면 정렬을 확인할 수 없다. */
                        $ago = (DQ_N - $i) * 37;   // 분
                        $ts  = date('Y-m-d H:i:s', strtotime(G5_TIME_YMDHIS . " -{$ago} minutes"));

                        sql_query("insert into ex_qna
                            (qa_parent, mb_id, pd_id, kind, pr_key, sj_no, qa_question, qa_chosen,
                             qa_status, cost_units, qa_credit_ok, qa_public,
                             bo_table, wr_id, created_at)
                            values (0,
                             '" . sql_real_escape_string($mb_id) . "',
                             '" . sql_real_escape_string($pd_id) . "',
                             '" . ($is_rep ? 'report' : 'qna') . "',
                             '" . sql_real_escape_string($p['pr_key']) . "',
                             " . (int)$p['sj_no'] . ",
                             '" . sql_real_escape_string($q_text) . "',
                             " . (int)$chosen . ",
                             'pending', 0, 1, 1,
                             '" . DQ_MARK . "', 0,
                             '" . $ts . "')", false);

                        $rows_made[] = array(
                            'pr_key' => $p['pr_key'], 'sj' => $p['sj_name'],
                            'kind' => $is_rep ? '오류 신고' : '질문',
                            'chosen' => $cl, 'q' => $q_text, 'at' => $ts,
                        );
                    }
                    $msg = count($rows_made) . '건을 넣었습니다. 질문 검수 화면에서 확인하십시오.';
                }
            }
        }
    }
}

$cur = sql_fetch("select count(*) as c from ex_qna where bo_table = '" . DQ_MARK . "'");
$all = sql_fetch("select count(*) as c from ex_qna");
$mbs = array();
$res = sql_query("select mb_id, mb_nick, mb_level from {$g5['member_table']}
                   order by mb_level desc, mb_id limit 30", false);
while ($res && $r = sql_fetch_array($res)) $mbs[] = $r;
?>
<meta charset="utf-8">
<title>더미 질문 넣기 / 지우기</title>
<style>
 body{font:14px/1.7 -apple-system,"Segoe UI",sans-serif;max-width:1000px;margin:34px auto;padding:0 18px;color:#1e2637}
 h1{font-size:21px;margin:0 0 6px} .sub{color:#6b7688;margin:0 0 22px;font-size:13px}
 .box{border:1px solid #e6eaf1;border-radius:10px;padding:16px 18px;margin:0 0 16px}
 .msg{border-radius:10px;padding:12px 16px;margin:0 0 18px;font-size:13.5px}
 .good{background:#e8f7ef;border:1px solid #a8dcc0;color:#0a5f3a}
 .bad{background:#fdecea;border:1px solid #f2b8b2;color:#8c1d13}
 .warn{background:#fff8e1;border:1px solid #f6d97a;color:#6b5410;
       border-radius:10px;padding:13px 16px;margin:22px 0 0;font-size:13.5px}
 table{width:100%;border-collapse:collapse;font-size:13px}
 th,td{text-align:left;padding:8px 10px;border-bottom:1px solid #e6eaf1;vertical-align:top}
 th{background:#f6f8fc;font-size:12.5px;color:#57637a}
 code{background:#f2f4f8;padding:1px 5px;border-radius:4px;font-size:12.5px}
 input[type=text]{padding:5px 9px;border:1px solid #dde1e8;border-radius:5px;font-size:13px}
 button{padding:7px 15px;border-radius:6px;border:1px solid #0f172a;background:#0f172a;
        color:#fff;font-size:13.5px;font-weight:700;cursor:pointer}
 button.ghost{background:#fff;color:#8c1d13;border-color:#f2b8b2}
 .kv{display:flex;gap:20px;flex-wrap:wrap;font-size:13px}.kv b{font-size:16px}
</style>

<h1>더미 질문 넣기 / 지우기</h1>
<p class="sub">질문 검수 화면과 LLM 초안 생성을 확인하기 위한 가상 질문입니다.
  <code>bo_table = '<?php echo DQ_MARK ?>'</code> 표식으로 한 버튼에 되돌립니다.</p>

<?php if ($msg): ?><div class="msg good"><?php echo htmlspecialchars($msg) ?></div><?php endif; ?>
<?php if ($err): ?><div class="msg bad"><?php echo htmlspecialchars($err) ?></div><?php endif; ?>

<div class="box">
  <div class="kv">
    <span>현재 더미 <b><?php echo (int)$cur['c'] ?></b>건</span>
    <span>질문 전체 <b><?php echo (int)$all['c'] ?></b>건</span>
  </div>
</div>

<div class="box">
  <form method="post">
    <input type="hidden" name="token" value="<?php echo get_token() ?>">
    <input type="hidden" name="act" value="ins">
    회원 <input type="text" name="mb" value="<?php echo htmlspecialchars($mb_id) ?>" size="12">
    문제집 <input type="text" name="pd" value="<?php echo htmlspecialchars($pd_id) ?>" size="10">
    <button type="submit"><?php echo DQ_N ?>건 넣기</button>
  </form>
  <p style="color:#6b7688;font-size:13px;margin:12px 0 0">
    실제 등록과 같은 값으로 넣습니다 — <code>qa_status='pending'</code> ·
    <code>cost_units=0</code> · <code>qa_credit_ok=1</code>(무료 기간).<br>
    과목이 골고루 섞이고, 8건은 <b>질문</b> · 2건은 <b>오류 신고</b>,
    등록 시각은 계단식으로 과거로 밀어 둡니다(검수 화면의 '오래 기다린 순' 정렬 확인용).
  </p>
  <p style="color:#6b7688;font-size:13px;margin:8px 0 0">
    회원 목록(상위 30):
    <?php foreach ($mbs as $m) { echo '<code>' . htmlspecialchars($m['mb_id']) . '</code>(lv'
        . (int)$m['mb_level'] . ') '; } ?>
  </p>
</div>

<?php if ((int)$cur['c'] > 0): ?>
<div class="box">
  <form method="post" onsubmit="return confirm('더미 질문 <?php echo (int)$cur['c'] ?>건을 지웁니다. 실제 질문은 건드리지 않습니다.')">
    <input type="hidden" name="token" value="<?php echo get_token() ?>">
    <input type="hidden" name="act" value="del">
    <button type="submit" class="ghost">더미 <?php echo (int)$cur['c'] ?>건 지우기</button>
  </form>
</div>
<?php endif; ?>

<?php if ($rows_made): ?>
<div class="box">
  <h2 style="font-size:15px;margin:0 0 10px">넣은 질문</h2>
  <table>
    <tr><th>문제</th><th>과목</th><th>종류</th><th>고른 보기</th><th>질문</th><th>등록</th></tr>
    <?php foreach ($rows_made as $r) { ?>
      <tr>
        <td><code><?php echo htmlspecialchars($r['pr_key']) ?></code></td>
        <td><?php echo htmlspecialchars($r['sj']) ?></td>
        <td><?php echo htmlspecialchars($r['kind']) ?></td>
        <td><?php echo htmlspecialchars($r['chosen']) ?></td>
        <td><?php echo htmlspecialchars($r['q']) ?></td>
        <td style="white-space:nowrap"><?php echo htmlspecialchars(substr($r['at'], 5, 11)) ?></td>
      </tr>
    <?php } ?>
  </table>
  <p style="margin:12px 0 0"><a href="<?php echo G5_ADMIN_URL ?>/exam_qna_list.php"><b>질문 검수 화면으로 →</b></a></p>
</div>
<?php endif; ?>

<div class="warn">
  <b>★ 확인이 끝나면 이 파일(<code>/www/exam_demo_questions.php</code>)을 지우십시오.</b><br>
  그리고 <b>더미 질문도 지우십시오</b> — 가상 질문이 실서비스에 남으면 이용자가 진짜로 믿습니다.
  초안을 생성했다면 그 초안도 함께 지워집니다(원가 로그는 <code>ex_log</code> 에 남습니다).
</div>
