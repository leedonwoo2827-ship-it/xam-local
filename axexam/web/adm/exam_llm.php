<?php
/**
 * 답변 초안 설정 — LLM API 키 등록 + 연결 테스트.
 *
 * ── 왜 화면에서 받는가 ─────────────────────────────────────────────────────
 * 키를 소스에 넣으면 git·백업·FTP 어디로든 새어나간다. 그래서 파일로 빼는데,
 * 그 파일을 FTP 로 손편집하게 하면 (a) 줄바꿈·따옴표가 섞여 깨지고
 * (b) 키를 바꿀 때마다 개발자를 불러야 한다. 그래서 화면에서 받는다.
 *
 * 저장 위치: `/data/exam_secret.php`
 *   · `data/` 는 웹에서 직접 조회가 막혀 있다 (실측 403)
 *   · `.gitignore` 의 `*secret*.php` 가 git 유입을 막는다
 *   · 저장 후에는 **마스킹만** 보여준다. 다시 전체를 보여줄 이유가 없다
 *
 * ── 연결 테스트를 같은 화면에 둔 이유 ──────────────────────────────────────
 * 키가 틀렸다는 것을 **검수 화면에서** 처음 알게 되면 곤란하다. 인증·모델명·
 * 한글 생성·토큰 기록이 한 번에 확인돼야 "이제 쓸 수 있다"고 말할 수 있다.
 */
$sub_menu = '600250';
require_once './_common.php';

auth_check_menu($auth, $sub_menu, 'r');

require_once './exam_lib/llm.php';

$msg = ''; $err = ''; $test = null;

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    auth_check_menu($auth, $sub_menu, 'w');
    if (function_exists('check_admin_token')) check_admin_token();
    else                                     check_token();

    $act = isset($_POST['act']) ? $_POST['act'] : '';

    if ($act === 'save') {
        $r = ex_llm_key_save(isset($_POST['api_key']) ? $_POST['api_key'] : '');
        if ($r['ok']) $msg = $r['msg'];
        else          $err = $r['msg'];

    } elseif ($act === 'test') {
        $pd = isset($_POST['pd']) ? $_POST['pd'] : '';
        /* 짧게 부른다. 연결 확인에 긴 답을 받을 이유가 없고, 실패해도 원가가 거의 0이다.
           한글로 답하게 해서 **한글 생성까지** 한 번에 본다 —
           인증만 통과하고 한글이 깨지는 조합이 실제로 있다. */
        $test = ex_llm_call($pd, array(
            array('role' => 'system', 'content' => '너는 한국어로만 답한다. 아주 짧게 답한다.'),
            array('role' => 'user',   'content' => 'SQLD 의 정식 명칭을 한 줄로 답하라.'),
        ), 120, 30);
    }
}

$key_now  = ex_llm_key();
$has_key  = ($key_now !== '');
$secret_p = ex_llm_secret_path();

/* 품목별 모델 설정 — 여기가 곧 설정이다(코드 수정 없이 갈아탄다) */
$prods = array();
$res = sql_query("select pd_id, pd_name, provider, model_id, cost_units, cost_cap, pd_config
                    from ex_product order by pd_sort, pd_id", false);
while ($res && $r = sql_fetch_array($res)) $prods[] = $r;

/* 초안 대기 — 키를 붙인 직후 무엇이 처리되는지 숫자로 보여준다 */
$q = sql_fetch("select
        sum(case when qa_status = 'pending'     then 1 else 0 end) as pending,
        sum(case when qa_status = 'draft_ready' then 1 else 0 end) as ready,
        sum(case when qa_draft is not null and qa_draft <> '' then 1 else 0 end) as drafted,
        count(*) as total
      from ex_qna");

$g5['title'] = '답변 초안 설정';
require_once './admin.head.php';

function exl_h($s) { return htmlspecialchars((string)$s, ENT_QUOTES, 'UTF-8'); }
?>

<style>
.exllm{max-width:1100px}
.exllm .box{background:#fff;border:1px solid #e3e6ec;border-radius:8px;padding:18px 20px;margin:0 0 16px}
.exllm h2{font-size:15px;margin:0 0 12px;font-weight:700}
.exllm .msg{padding:11px 16px;border-radius:6px;margin:0 0 14px;font-size:14px;line-height:1.6}
.exllm .msg.good{background:#e9f7ef;border:1px solid #0a7f3f;color:#075c2d}
.exllm .msg.err{background:#fdeced;border:1px solid #c22638;color:#8c1220}
.exllm .row{display:flex;gap:9px;align-items:center;flex-wrap:wrap}
.exllm input[type=text],.exllm input[type=password]{padding:6px 10px;border:1px solid #dde1e8;
  border-radius:4px;font-size:13px;width:420px;font-family:Consolas,monospace}
.exllm select{padding:6px 8px;border:1px solid #dde1e8;border-radius:4px;font-size:13px}
.exllm .hint{color:#666;font-size:13px;line-height:1.7}
.exllm code{background:#f4f5f7;padding:1px 5px;border-radius:3px;font-family:Consolas,monospace}
.exllm .state{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:700}
.exllm .state.on{background:#e9f7ef;color:#075c2d}
.exllm .state.off{background:#fdeced;color:#8c1220}
.exllm table.list{border-collapse:collapse;width:100%;font-size:13px}
.exllm .list th,.exllm .list td{border:1px solid #e3e6ec;padding:7px 9px;text-align:left}
.exllm .list th{background:#f7f8fa;font-weight:600;white-space:nowrap}
.exllm .kv{display:flex;gap:18px;flex-wrap:wrap;font-size:13px;align-items:baseline}
.exllm .kv b{font-size:15px}
.exllm pre{background:#f7f8fa;border:1px solid #e3e6ec;border-radius:6px;padding:12px 14px;
  font-size:13px;line-height:1.7;white-space:pre-wrap;margin:10px 0 0}
</style>

<div class="exllm">

<?php if ($msg): ?><div class="msg good"><?php echo exl_h($msg) ?></div><?php endif; ?>
<?php if ($err): ?><div class="msg err"><?php echo exl_h($err) ?></div><?php endif; ?>

  <div class="box">
    <h2>API 키</h2>
    <p class="hint" style="margin:0 0 12px">
      상태
      <span class="state <?php echo $has_key ? 'on' : 'off' ?>">
        <?php echo $has_key ? '등록됨 · ' . exl_h(ex_llm_key_mask()) : '없음' ?></span><br>
      저장 위치 <code><?php echo exl_h($secret_p) ?></code> —
      웹에서 직접 조회가 막혀 있고(<code>data/</code>), git 에도 올라가지 않습니다.
      <b>소스·문서에 키를 적지 않습니다.</b>
    </p>
    <form method="post" action="exam_llm.php" autocomplete="off">
      <?php echo isset($token) ? '<input type="hidden" name="token" value="'.$token.'">' : '' ?>
      <input type="hidden" name="act" value="save">
      <div class="row">
        <input type="password" name="api_key" placeholder="<?php
          echo $has_key ? '새 키를 넣으면 교체됩니다 (비우고 저장하면 삭제)' : 'sk-…' ?>"
          autocomplete="new-password" spellcheck="false">
        <input type="submit" class="btn_submit" value="저장">
      </div>
    </form>
    <p class="hint" style="margin-top:10px">
      ⚠ 키는 <b>결제 수단과 같습니다.</b> 유출되면 남이 우리 계정으로 모델을 씁니다.
      메신저·문서에 붙여넣지 마시고, 노출됐다면 공급자 콘솔에서 <b>재발급</b>하십시오.
    </p>
  </div>

  <div class="box">
    <h2>연결 테스트</h2>
    <form method="post" action="exam_llm.php">
      <?php echo isset($token) ? '<input type="hidden" name="token" value="'.$token.'">' : '' ?>
      <input type="hidden" name="act" value="test">
      <div class="row">
        <select name="pd">
          <?php foreach ($prods as $p) { ?>
            <option value="<?php echo exl_h($p['pd_id']) ?>"><?php
              echo exl_h($p['pd_name']) ?> — <?php echo exl_h($p['model_id']) ?></option>
          <?php } ?>
        </select>
        <input type="submit" class="btn_submit" value="테스트 호출"
               <?php echo $has_key ? '' : 'disabled' ?>>
        <?php if (!$has_key) { ?><span class="hint">키를 먼저 등록하십시오.</span><?php } ?>
      </div>
    </form>

    <?php if ($test !== null) { ?>
      <?php if (!empty($test['ok'])) { ?>
        <div class="msg good" style="margin:14px 0 0">
          <b>성공</b> — 인증·모델명·한글 생성·토큰 기록이 모두 확인됐습니다.
        </div>
        <div class="kv" style="margin-top:10px">
          <span>모델 <b><?php echo exl_h($test['model']) ?></b></span>
          <span>입력 <b><?php echo (int)$test['tok_in'] ?></b>토큰</span>
          <span>캐시 <b><?php echo (int)$test['tok_cache'] ?></b>토큰</span>
          <span>출력 <b><?php echo (int)$test['tok_out'] ?></b>토큰</span>
          <span>원가 <b><?php echo number_format($test['cost'], 4) ?></b>원</span>
        </div>
        <?php if (!empty($test['over_cap'])) { ?>
          <div class="msg err" style="margin:12px 0 0">
            원가가 상한(<?php echo number_format($test['cost_cap'], 2) ?>원)을 넘었습니다 —
            <code>ex_product.cost_cap</code> 또는 모델을 확인하십시오.
          </div>
        <?php } ?>
        <pre><?php echo exl_h($test['text']) ?></pre>
      <?php } else { ?>
        <div class="msg err" style="margin:14px 0 0">
          <b>실패</b> — <?php echo exl_h($test['msg']) ?>
        </div>
        <p class="hint">
          자주 나오는 원인:<br>
          · <b>HTTP 401</b> 키가 틀렸거나 앞뒤 공백이 섞였다 → 다시 저장<br>
          · <b>HTTP 404 / 응답이 빔</b> 모델명이 틀렸다 → 아래 표의 <code>model_id</code> 확인<br>
          · <b>HTTP 402 / insufficient balance</b> 잔액이 없다 → 공급자 콘솔에서 충전<br>
          · <b>curl 실패</b> 호스팅에서 외부 HTTPS 가 막혔다 → 카페24 문의
        </p>
      <?php } ?>
    <?php } ?>
  </div>

  <div class="box">
    <h2>문제집별 모델</h2>
    <p class="hint" style="margin:0 0 10px">
      <b>이 표가 곧 설정입니다.</b> 모델이 막히거나 값이 오르면
      <code>ex_product</code> 한 행만 바꿔 갈아탑니다 — PHP 파일을 고치지 않습니다.
    </p>
    <table class="list">
      <tr><th>문제집</th><th>공급자</th><th>모델</th><th>차감(원)</th><th>원가 상한(원)</th></tr>
      <?php foreach ($prods as $p) { ?>
        <tr>
          <td><b><?php echo exl_h($p['pd_name']) ?></b> <code><?php echo exl_h($p['pd_id']) ?></code></td>
          <td><code><?php echo exl_h($p['provider']) ?></code></td>
          <td><code><?php echo exl_h($p['model_id']) ?></code></td>
          <td><?php echo (int)$p['cost_units'] ?></td>
          <td><?php echo number_format((float)$p['cost_cap'], 2) ?></td>
        </tr>
      <?php } ?>
    </table>
    <p class="hint" style="margin-top:10px">
      DeepSeek 은 OpenAI 호환이라 <code>provider = openai_compat</code> 입니다.
      <code>anthropic</code> 으로 바꾸면 엔드포인트·헤더가 자동으로 갈립니다.
    </p>
  </div>

  <div class="box">
    <h2>초안 현황</h2>
    <div class="kv">
      <span>질문 전체 <b><?php echo number_format((int)$q['total']) ?></b></span>
      <span>대기 <b><?php echo number_format((int)$q['pending']) ?></b></span>
      <span>초안 있음 <b><?php echo number_format((int)$q['drafted']) ?></b></span>
      <span>검수 대기 <b><?php echo number_format((int)$q['ready']) ?></b></span>
    </div>
    <p class="hint" style="margin-top:10px">
      초안 생성은 <a href="exam_qna_list.php"><b>질문 검수</b></a> 화면에서 합니다 —
      질문을 보면서 만드는 것이 순서이고, 여기서 일괄로 돌리면 무엇에 대한 초안인지 모른 채
      원가만 쓰게 됩니다.<br>
      ⚠ <b>초안은 이용자에게 절대 보이지 않습니다.</b> 회원 API 는 <code>qa_answer</code> 만
      SELECT 하고 <code>qa_draft</code> 는 SELECT 목록에 없습니다 —
      검수 없이 공개되는 경로가 구조적으로 존재하지 않습니다.
    </p>
  </div>
</div>

<?php
require_once './admin.tail.php';
