<?php
/**
 * 문항 DB 뷰어 · 편집 — `ex_problem` 한 행을 그대로 보고 고친다.
 *
 * ── 왜 필요한가 ────────────────────────────────────────────────────────────
 * 지금까지 문항을 고칠 길이 하나뿐이었다: 로컬에서 `_rounds`·`02/`·`05/lesson` 을
 * 고치고 → 빌드 → `problems.json` 임포트. 오타 하나를 고치는 데도 그 전체를 돈다.
 * 운영 중에 "정답이 틀렸다" 는 신고가 오면 그 사이 학생들이 계속 틀린 채점을 받는다.
 * `exam_problem_list.php` 의 `pr_open` 토글로 **숨기는 것**만 즉시 가능했다.
 *
 * 이 화면은 그 자리를 채운다. 그리고 DB 뷰어를 겸한다 — 카페24에 phpMyAdmin 이 없어서
 * "지금 서버에 실제로 뭐가 들어 있나" 를 볼 방법이 없었다.
 *
 * ── ★ 고치면 로컬과 갈린다 (반드시 읽을 것) ────────────────────────────────
 * 저장하면 `edited_by` 에 관리자 ID 가 남고, 그 뒤로 **재임포트가 이 행을 건너뛴다**
 * (`exam_lib/problem.php:140`). 그래야 로컬 재임포트가 웹 수정을 지우지 않는다.
 *
 * 그 대가는 `problem.php:22` 가 적어 두었다:
 *   "웹 수정본은 02/ 원본과 어긋난 채로 남는다. 주기적으로 02/ 로 역반영하지 않으면
 *    언젠가 '원본 복원' 이 낡은 내용을 되살린다."
 *
 * → 그래서 이 화면은 저장할 때마다 **로컬 반영용 JSON 을 내려받게** 한다.
 *   그 파일을 XAM LOCAL 쪽에서 `#/questions` 에 적용하면 갈림이 정리된다.
 *   미루지 말 것 — 미루면 어느 쪽이 최신인지 알 수 없게 된다.
 *
 * ── 안 고치는 것 ───────────────────────────────────────────────────────────
 * `pr_key` · `pd_id` · `rd_no` · `pr_no` · `bundle` 은 편집 대상이 아니다.
 * `pr_key` 는 회원의 오답노트(`ex_wrong.pr_id`)·응시기록(`ex_attempt_item.pr_id`)이
 * 참조하는 축이다. 바꾸면 같은 문제가 새 행으로 들어가 기록이 통째로 끊긴다.
 * `pr_hash` 도 건드리지 않는다 — 로컬 원본과 갈렸는지 판정하는 근거다.
 */
$sub_menu = '600460';
require_once './_common.php';

auth_check_menu($auth, $sub_menu, 'r');

require_once G5_ADMIN_PATH . '/exam_lib/problem.php';   // ex_s()

function epf_h($s) { return htmlspecialchars((string)$s, ENT_QUOTES, 'UTF-8'); }

/** JSON 컬럼을 배열로. 깨져 있으면 기본값(원본을 지우지 않기 위해 예외를 내지 않는다). */
function epf_json($s, $default = array()) {
    $v = json_decode((string)$s, true);
    return is_array($v) ? $v : $default;
}

$msg = ''; $err = ''; $reflect = null;

/* ── 대상 찾기 ─────────────────────────────────────────────────────────────
 * pr_id 로도, pr_key 로도 열 수 있게 한다. 운영자는 화면에서 `m04-2#12` 를 보고
 * 오므로 pr_key 가 더 자연스럽다. */
$pr_id  = (int)(isset($_REQUEST['pr_id']) ? $_REQUEST['pr_id'] : 0);
$pr_key = isset($_REQUEST['pr_key']) ? trim((string)$_REQUEST['pr_key']) : '';
$pd_id  = isset($_REQUEST['pd']) ? trim((string)$_REQUEST['pd']) : '';

/* ── 저장 ──────────────────────────────────────────────────────────────── */
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['act']) && $_POST['act'] === 'save') {
    auth_check_menu($auth, $sub_menu, 'w');
    check_admin_token();

    $row = $pr_id ? sql_fetch("select * from ex_problem where pr_id = $pr_id") : null;
    if (!$row) {
        $err = '대상 문항을 찾지 못했습니다.';
    } else {
        $q    = trim((string)$_POST['question']);
        $ex   = (string)$_POST['explanation'];
        $diff = trim((string)$_POST['difficulty']);
        $ai   = (int)$_POST['answer_index'];

        // 보기는 줄 단위로 받는다 — 배열 입력보다 오타가 적고 순서가 눈에 보인다.
        $lines = preg_split('/\r\n|\r|\n/', (string)$_POST['choices']);
        $ch = array();
        foreach ($lines as $L) { $L = trim($L); if ($L !== '') $ch[] = $L; }

        if ($q === '') {
            $err = '발문이 비었습니다.';
        } elseif (count($ch) < 2) {
            $err = '보기가 2개 이상이어야 합니다.';
        } elseif ($ai < 0 || $ai >= count($ch)) {
            $err = "정답 번호가 보기 범위를 벗어났습니다 (0 ~ " . (count($ch) - 1) . ").";
        } elseif ($diff !== '' && !in_array($diff, array('상', '중', '하'), true)) {
            $err = "난이도는 상/중/하 만 됩니다.";
        } else {
            // 라벨은 번호에서 만든다 — 손으로 넣으면 번호와 어긋난다(그게 가장 흔한 사고다).
            $glyph = array('①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧');
            $label = isset($glyph[$ai]) ? $glyph[$ai] : (string)($ai + 1);

            $me = isset($member['mb_id']) ? $member['mb_id'] : 'admin';
            sql_query("update ex_problem set
                          question     = '" . ex_s($q) . "',
                          choices_json = '" . ex_s(json_encode($ch, JSON_UNESCAPED_UNICODE)) . "',
                          n_choices    = " . count($ch) . ",
                          answer_index = $ai,
                          answer_label = '" . ex_s($label) . "',
                          explanation  = '" . ex_s($ex) . "',
                          difficulty   = '" . ex_s($diff) . "',
                          edited_by    = '" . ex_s($me) . "',
                          edited_at    = '" . G5_TIME_YMDHIS . "',
                          updated_at   = '" . G5_TIME_YMDHIS . "'
                        where pr_id = $pr_id");

            $msg = '저장했습니다. 이용자 화면에 즉시 반영됩니다 (api/problems.php 가 매 요청 DB 를 읽습니다).';

            /* 로컬 반영용 — 이 값을 XAM LOCAL 의 #/questions 에 그대로 넣으면 갈림이 정리된다. */
            $reflect = array(
                'pd_id' => $row['pd_id'], 'pr_key' => $row['pr_key'],
                'rd_no' => (int)$row['rd_no'], 'pr_no' => (int)$row['pr_no'],
                'bundle' => $row['bundle'], 'src_id' => $row['src_id'],
                'edited_by' => $me, 'edited_at' => G5_TIME_YMDHIS,
                'fields' => array(
                    'question' => $q, 'choices' => $ch,
                    'answer_index' => $ai, 'answer_label' => $label,
                    'explanation' => $ex, 'difficulty' => $diff,
                ),
                'note' => ('웹에서 고친 값이다. XAM LOCAL 의 #/questions 에 같은 값을 넣어 '
                         . '02/ 원본과 맞춘 뒤, 관리자 화면에서 "원본 복원" 을 눌러 '
                         . 'edited_by 를 비우면 다시 임포트가 관리한다.'),
            );
        }
    }
}

/* ── 원본 복원 (edited_by 비우기) ──────────────────────────────────────── */
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['act']) && $_POST['act'] === 'unlock') {
    auth_check_menu($auth, $sub_menu, 'w');
    check_admin_token();
    $row = $pr_id ? sql_fetch("select pd_id, pr_key from ex_problem where pr_id = $pr_id") : null;
    if ($row) {
        $n = ex_problem_unlock($row['pd_id'], $row['pr_key']);
        $msg = '잠금을 풀었습니다(' . (int)$n . '행). '
             . '이제 problems.json 재임포트가 이 문항을 다시 덮어씁니다 — '
             . '로컬 원본이 맞는지 확인한 뒤 임포트하세요.';
    }
}

/* ── 조회 ──────────────────────────────────────────────────────────────── */
$row = null;
if ($pr_id) {
    $row = sql_fetch("select * from ex_problem where pr_id = $pr_id");
} elseif ($pr_key !== '') {
    $w = "pr_key = '" . ex_s($pr_key) . "'";
    if ($pd_id !== '') $w .= " and pd_id = '" . ex_s($pd_id) . "'";
    $row = sql_fetch("select * from ex_problem where $w order by pr_id limit 1");
    if ($row) $pr_id = (int)$row['pr_id'];
}

/* 실 정답률 — 이 문항이 정말 틀렸는지 판단하는 근거다. */
$stat = null;
if ($row) {
    $stat = sql_fetch("select count(*) as tries, sum(is_ok) as oks
                         from ex_attempt_item where pr_id = " . (int)$row['pr_id'] . " and chosen >= 0");
}

$g5['title'] = '문항 DB 뷰어';
require_once './admin.head.php';
?>
<style>
 .epf-wrap{max-width:1000px}
 .epf-msg{padding:9px 12px;border-radius:5px;margin:10px 0;font-size:13px}
 .epf-ok{background:#e3f1ec;border:1px solid #0f7355;color:#0f7355}
 .epf-er{background:#f6e7ef;border:1px solid #6b1d4a;color:#6b1d4a}
 .epf-warn{background:#f8f6e6;border:1px solid #6f6112;color:#6f6112}
 .epf-find{background:#f6f6f2;border:1px solid #ddd;border-radius:6px;padding:11px 13px;margin:12px 0}
 .epf-find input{padding:5px 8px;border:1px solid #ccc;border-radius:4px}
 table.epf-raw{border-collapse:collapse;width:100%;margin:12px 0;font-size:12px}
 table.epf-raw th,table.epf-raw td{border:1px solid #e3e3e0;padding:5px 8px;text-align:left;vertical-align:top}
 table.epf-raw th{background:#f6f6f2;width:150px;white-space:nowrap;font-weight:600}
 table.epf-raw td{word-break:break-all;font-family:ui-monospace,Consolas,monospace}
 .epf-form label{display:block;margin:12px 0 3px;font-weight:600;font-size:13px}
 .epf-form input[type=text],.epf-form textarea,.epf-form select{
   width:100%;padding:6px 8px;border:1px solid #ccc;border-radius:4px;font:inherit}
 .epf-form textarea{line-height:1.55}
 .epf-form .hint{color:#666;font-size:12px;margin-top:2px}
 .epf-btn{margin-top:16px;display:flex;gap:8px;flex-wrap:wrap}
 .epf-btn button{padding:8px 16px;border:0;border-radius:5px;font:inherit;font-weight:700;cursor:pointer}
 .epf-save{background:#c41c0b;color:#fff}
 .epf-unlock{background:#6f6112;color:#fff}
 .epf-pct{font-size:22px;font-weight:800}
 pre.epf-json{background:#1b1f19;color:#e8e8e0;padding:11px;border-radius:5px;
   font:11px/1.5 ui-monospace,Consolas,monospace;max-height:280px;overflow:auto}
</style>

<div class="epf-wrap">

<?php if ($msg): ?><div class="epf-msg epf-ok"><?php echo epf_h($msg) ?></div><?php endif; ?>
<?php if ($err): ?><div class="epf-msg epf-er"><?php echo epf_h($err) ?></div><?php endif; ?>

<div class="epf-find">
  <form method="get">
    <b>문항 찾기</b>
    &nbsp; pr_key <input type="text" name="pr_key" value="<?php echo epf_h($pr_key) ?>"
           placeholder="m04-2#12" size="16">
    &nbsp; 품목 <input type="text" name="pd" value="<?php echo epf_h($pd_id) ?>"
           placeholder="bigdata" size="10">
    &nbsp; 또는 pr_id <input type="text" name="pr_id" value="<?php echo $pr_id ?: '' ?>" size="7">
    &nbsp; <button type="submit">열기</button>
    &nbsp; <a href="<?php echo G5_ADMIN_URL ?>/exam_problem_list.php">← 문제 목록(정답률 낮은 순)</a>
  </form>
</div>

<?php if (!$row): ?>
  <p style="color:#666">문항을 지정하세요. <b>문제 목록</b>에서 정답률이 낮은 것부터 보는 것이
  빠릅니다 — 정답률 20% 미만은 대개 정답이 틀렸거나 보기가 모호합니다.</p>
<?php else: ?>

  <h2 style="font-size:17px;margin:16px 0 2px">
    <?php echo epf_h($row['pd_id']) ?> · <?php echo (int)$row['rd_no'] ?>회
    <?php echo (int)$row['pr_no'] ?>번
    <small style="color:#666">(<?php echo epf_h($row['pr_key']) ?> · pr_id <?php echo (int)$row['pr_id'] ?>)</small>
  </h2>

  <?php if ($row['edited_by'] !== ''): ?>
    <div class="epf-msg epf-warn">
      <b>웹 수정본입니다</b> — <?php echo epf_h($row['edited_by']) ?>
      (<?php echo epf_h($row['edited_at']) ?>).
      <code>problems.json</code> 재임포트가 <b>이 문항을 건너뜁니다</b>(수정을 지키기 위한 것).
      로컬 <code>02/</code> 원본과 어긋난 상태이므로, 로컬에도 같은 값을 넣은 뒤
      아래 <b>원본 복원</b>을 눌러 잠금을 푸세요.
    </div>
  <?php endif; ?>

  <?php if ((int)$row['pr_open'] === 0): ?>
    <div class="epf-msg epf-warn"><b>숨김 상태입니다</b> —
      이용자 화면에 나오지 않습니다. 문제 목록에서 다시 공개할 수 있습니다.</div>
  <?php endif; ?>

  <?php if ($stat && (int)$stat['tries'] > 0):
      $pct = round((int)$stat['oks'] * 100 / (int)$stat['tries'], 1); ?>
    <p>실 정답률 <span class="epf-pct"><?php echo $pct ?>%</span>
       <small style="color:#666">(<?php echo (int)$stat['tries'] ?>회 응시 중
       <?php echo (int)$stat['oks'] ?>회 정답)</small>
       <?php if ($pct < 20): ?>
         <b style="color:#6b1d4a">— 20% 미만입니다. 정답 자체가 틀렸을 가능성을 먼저 보세요.</b>
       <?php endif; ?></p>
  <?php else: ?>
    <p style="color:#666">아직 응시 기록이 없습니다.</p>
  <?php endif; ?>

  <!-- ── 편집 ─────────────────────────────────────────────────────── -->
  <form method="post" class="epf-form">
  <?php echo get_admin_token(); ?>
  <input type="hidden" name="act" value="save">
  <input type="hidden" name="pr_id" value="<?php echo (int)$row['pr_id'] ?>">

    <label>발문</label>
    <textarea name="question" rows="3"><?php echo epf_h($row['question']) ?></textarea>

    <label>보기 <span class="hint">— 한 줄에 하나. 순서가 정답 번호의 기준입니다</span></label>
    <textarea name="choices" rows="5"><?php
      echo epf_h(implode("\n", epf_json($row['choices_json']))) ?></textarea>

    <label>정답</label>
    <select name="answer_index">
      <?php $ch = epf_json($row['choices_json']);
            $glyph = array('①','②','③','④','⑤','⑥','⑦','⑧');
            foreach ($ch as $i => $c): ?>
        <option value="<?php echo $i ?>"
          <?php echo ((int)$row['answer_index'] === $i ? 'selected' : '') ?>>
          <?php echo epf_h(($glyph[$i] ?? ($i+1)) . '  ' . mb_substr($c, 0, 60)) ?>
        </option>
      <?php endforeach; ?>
    </select>
    <div class="hint">기호(<?php echo epf_h($row['answer_label']) ?>)는 번호에서 자동으로 만듭니다 —
      손으로 넣으면 번호와 어긋납니다.</div>

    <label>난이도</label>
    <select name="difficulty">
      <?php foreach (array('', '상', '중', '하') as $d): ?>
        <option value="<?php echo $d ?>" <?php echo ($row['difficulty'] === $d ? 'selected' : '') ?>>
          <?php echo $d === '' ? '(없음)' : $d ?></option>
      <?php endforeach; ?>
    </select>

    <label>해설</label>
    <textarea name="explanation" rows="7"><?php echo epf_h($row['explanation']) ?></textarea>

    <div class="hint" style="margin-top:10px">
      ★ 지문·표·SQL·그림은 여기서 고치지 않습니다 — 로컬 <code>02/</code> 원본과
      <code>05/lesson</code> 이 함께 움직여야 하고, 그림은 파일(<code>figs/</code>)이라
      FTP 가 따라옵니다. 그건 XAM LOCAL 의 <code>#/questions</code> 에서 하세요.
    </div>

    <div class="epf-btn">
      <button type="submit" class="epf-save">저장 (즉시 반영)</button>
    </div>
  </form>

  <?php if ($row['edited_by'] !== ''): ?>
  <form method="post" style="margin-top:8px">
    <?php echo get_admin_token(); ?>
    <input type="hidden" name="act" value="unlock">
    <input type="hidden" name="pr_id" value="<?php echo (int)$row['pr_id'] ?>">
    <div class="epf-btn">
      <button type="submit" class="epf-unlock"
        onclick="return confirm('잠금을 풉니다.\n다음 재임포트가 이 문항을 로컬 값으로 덮어씁니다.\n로컬 원본이 최신인지 확인했습니까?')">
        원본 복원 (잠금 해제)</button>
    </div>
  </form>
  <?php endif; ?>

  <?php if ($reflect): ?>
    <h3 style="font-size:15px;margin:22px 0 4px">로컬 반영용 — 이 값을 <code>#/questions</code> 에 넣으세요</h3>
    <p class="hint">미루면 어느 쪽이 최신인지 알 수 없게 됩니다.</p>
    <pre class="epf-json"><?php echo epf_h(json_encode($reflect,
        JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT)) ?></pre>
  <?php endif; ?>

  <?php
  /* ── 그림 파일명 ─────────────────────────────────────────────────────────
   * ★ 파일명을 보여 주는 이유: 그림은 캐시(1시간)에 걸린다. 같은 이름으로 덮어쓰면
   *   이미 본 사람에게 잠시 옛 그림이 보인다. 급할 때는 **다른 이름**으로 만들어야
   *   하는데, 그러려면 지금 이름이 무엇인지 알아야 한다.
   *   앱(#/questions)에는 그림 아래에 이름이 보이는데 이 화면에는 없었다. */
  $figs = epf_json($row['figures_json'], array());
  if ($figs): ?>
    <h3 style="font-size:15px;margin:22px 0 4px">그림 <small style="color:#666">(파일명)</small></h3>
    <p class="hint">
      바꿀 때는 <b>다른 이름으로 만드는 것을 권합니다</b> — 같은 이름은 캐시(1시간) 때문에
      잠시 옛 그림이 보입니다. 이름은 로컬 <code>_rounds</code> 의
      <code>assets[].name</code> 이므로 <b>#2(클로드 데스크탑)</b>에 새 이름으로 요청합니다.
    </p>
    <table class="epf-raw">
      <tr><th>파일명</th><th>서버 경로</th></tr>
      <?php foreach ($figs as $f):
          $fn = is_array($f) ? (isset($f['name']) ? $f['name'] : '') : (string)$f;
          if ($fn === '') continue;
          if (substr($fn, -4) !== '.svg' && strpos($fn, '.') === false) $fn .= '.svg'; ?>
        <tr>
          <th style="width:auto"><code><?php echo epf_h($fn) ?></code></th>
          <td>/exam/pd/<?php echo epf_h($row['pd_id']) ?>/figs/<?php echo epf_h($fn) ?></td>
        </tr>
      <?php endforeach; ?>
    </table>
  <?php endif; ?>

  <!-- ── DB 뷰어: 이 행의 전 컬럼 ────────────────────────────────── -->
  <h3 style="font-size:15px;margin:24px 0 4px">DB 원본 (ex_problem 한 행 전부)</h3>
  <p class="hint">카페24에 phpMyAdmin 이 없어 서버에 실제로 무엇이 들어 있는지 볼 방법이
    없었습니다. 이 표가 그 자리입니다. 회색 컬럼은 편집 대상이 아닙니다.</p>
  <table class="epf-raw">
    <?php
    $locked = array('pr_id','pd_id','rd_no','pr_key','bundle','pr_no','src_id','src_from','pr_hash');
    foreach ($row as $k => $v):
        if (is_int($k)) continue;                       // mysqli 의 숫자 인덱스 중복
        $isLocked = in_array($k, $locked, true); ?>
      <tr>
        <th style="<?php echo $isLocked ? 'color:#999' : '' ?>"><?php echo epf_h($k) ?></th>
        <td><?php echo epf_h($v === null ? '(null)' : (string)$v) ?></td>
      </tr>
    <?php endforeach; ?>
  </table>

<?php endif; ?>
</div>
<?php
require_once './admin.tail.php';
