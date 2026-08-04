<?php
/**
 * LLM 호출 — 답변 초안 생성용. **관리자 영역에서만 쓴다.**
 *
 * ── 왜 서버 PHP 에서 부르는가 ──────────────────────────────────────────────
 * 로컬 FastAPI 를 띄워두면 관리자가 그 프로세스를 살려둬야 초안이 생긴다.
 * 검수는 "관리자가 화면을 열 때" 하는 일이므로 그 요청 안에서 끝나는 게 맞다.
 *
 * ── 키는 코드에 없다 ───────────────────────────────────────────────────────
 * `/data/exam_secret.php` 에 있다. 그 폴더는 `.htaccess` 가 외부 조회를 막고(실측 403)
 * `.gitignore` 의 `*secret*.php` 가 git 유입도 막는다.
 * **키를 소스에 넣으면 git·백업·FTP 어디로든 새어나간다.**
 *
 * ── provider 를 왜 추상화하는가 ────────────────────────────────────────────
 * `ex_product.provider` 가 `openai_compat` | `anthropic` 이다. DeepSeek·OpenAI·
 * 로컬 vLLM 이 전부 openai_compat 이라 대부분 base_url·model 만 바꾸면 된다.
 * 모델이 막히거나 값이 오를 때 **품목별로** 갈아탈 수 있어야 한다(DB 1행 수정).
 *
 * ⚠ 원가를 항상 기록한다(`qa_tok_*`·`qa_cost`). 기록하지 않으면 "질문 1건 10원 차감"이
 *   실제로 남는 장사인지 알 수 없고, 모델을 바꿀 근거도 생기지 않는다.
 */
if (!defined('_GNUBOARD_')) exit;

/** 키 파일 경로 — 화면(adm/exam_llm.php)이 여기에 쓴다 */
function ex_llm_secret_path()
{
    return G5_DATA_PATH . '/exam_secret.php';
}

/**
 * 저장된 키. 없으면 ''.
 *
 * 파일은 PHP 라 직접 조회해도 소스가 안 나오고, `.htaccess` 가 한 겹 더 막는다.
 */
function ex_llm_key()
{
    static $key = null;
    if ($key !== null) return $key;
    $key = '';
    $p = ex_llm_secret_path();
    if (is_readable($p)) {
        include_once($p);
        if (defined('EX_LLM_KEY')) $key = (string)EX_LLM_KEY;
    }
    return $key;
}

/** 화면에 보여줄 마스킹 값. 전체를 다시 보여줄 이유가 없다. */
function ex_llm_key_mask($key = null)
{
    $k = ($key === null) ? ex_llm_key() : $key;
    $n = strlen($k);
    if ($n === 0) return '';
    if ($n <= 11) return str_repeat('•', $n);
    return substr($k, 0, 3) . str_repeat('•', 8) . substr($k, -4);
}

/**
 * 키 저장. 파일로 쓴다 — 테이블에 두면 DB 덤프에 평문으로 실린다.
 *
 * @return array ok · msg
 */
function ex_llm_key_save($key)
{
    $key = trim((string)$key);
    // 형식만 본다. 유효성은 [연결 테스트]가 실제 호출로 판정한다 —
    // 접두어 규칙은 공급자가 바꿀 수 있어서 여기서 막으면 나중에 발목을 잡는다.
    if ($key !== '' && !preg_match('/^[A-Za-z0-9_\-]{16,200}$/', $key)) {
        return array('ok' => false, 'msg' => '키 형식이 아닙니다. 앞뒤 공백이나 줄바꿈이 섞였는지 확인하십시오.');
    }
    $p = ex_llm_secret_path();
    if ($key === '') {
        if (is_file($p)) @unlink($p);
        return array('ok' => true, 'msg' => '키를 지웠습니다.');
    }
    $body = "<?php\n"
          . "/* LLM API 키. adm/exam_llm.php 가 쓴다 — 손으로 고치지 않는다.\n"
          . "   git 에 올리지 않는다(.gitignore: *secret*.php). */\n"
          . "if (!defined('_GNUBOARD_')) exit;\n"
          . "define('EX_LLM_KEY', '" . str_replace("'", "\\'", $key) . "');\n";
    if (@file_put_contents($p, $body) === false) {
        return array('ok' => false, 'msg' => G5_DATA_PATH . ' 에 쓸 수 없습니다. 폴더 권한을 확인하십시오(707).');
    }
    @chmod($p, 0600);
    return array('ok' => true, 'msg' => '키를 저장했습니다.');
}

/**
 * 품목의 모델 설정. `ex_product` 한 행이 곧 설정이다 — 코드 수정 없이 갈아탄다.
 */
function ex_llm_model($pd_id)
{
    $r = sql_fetch("select pd_id, pd_name, provider, model_id, cost_cap
                      from ex_product where pd_id = '" . sql_real_escape_string($pd_id) . "'");
    if (!$r) return null;
    return array(
        'pd_id'    => $r['pd_id'],
        'provider' => $r['provider'] ?: 'openai_compat',
        'model'    => $r['model_id'] ?: 'deepseek-chat',
        'cost_cap' => (float)$r['cost_cap'],
    );
}

/* 공급자별 엔드포인트. base_url 만 바뀌는 게 대부분이라 표로 둔다. */
function ex_llm_endpoint($provider)
{
    switch ($provider) {
        case 'anthropic':     return 'https://api.anthropic.com/v1/messages';
        case 'openai':        return 'https://api.openai.com/v1/chat/completions';
        case 'openai_compat': // DeepSeek 은 OpenAI 호환이다
        default:              return 'https://api.deepseek.com/v1/chat/completions';
    }
}

/* 1,000토큰당 원. 실측 단가가 바뀌면 여기만 고친다.
 * DeepSeek 은 캐시 히트가 훨씬 싸므로 따로 센다 — 같은 문제에 질문이 몰리면
 * 프롬프트 앞부분(문제 본문)이 캐시되어 원가가 실제로 내려간다. */
function ex_llm_price($model)
{
    // (in, cache_hit, out) — KRW / 1K tokens
    if (strpos($model, 'deepseek') !== false) return array(0.38, 0.038, 0.75);
    if (strpos($model, 'gpt-4o-mini') !== false) return array(0.21, 0.105, 0.84);
    return array(1.0, 0.5, 2.0);   // 모르는 모델 — 비싸게 잡아둔다(경고가 먼저 뜨게)
}

/**
 * 실제 호출. 성공하면 text·토큰·원가를 돌려준다.
 *
 * @param  array  $msg  [['role'=>'system'|'user','content'=>'...'], ...]
 * @return array  ok · text · model · tok_in · tok_cache · tok_out · cost · msg
 */
function ex_llm_call($pd_id, $msg, $max_tokens = 1200, $timeout = 60)
{
    $key = ex_llm_key();
    if ($key === '') {
        return array('ok' => false, 'msg' => 'API 키가 없습니다. 관리자 → 문제은행 → 답변 초안 설정에서 등록하십시오.');
    }
    $cfg = ex_llm_model($pd_id);
    if (!$cfg) return array('ok' => false, 'msg' => '없는 문제집입니다: ' . $pd_id);

    $url = ex_llm_endpoint($cfg['provider']);
    $hdr = array('Content-Type: application/json');

    if ($cfg['provider'] === 'anthropic') {
        $hdr[] = 'x-api-key: ' . $key;
        $hdr[] = 'anthropic-version: 2023-06-01';
        $sys = ''; $turns = array();
        foreach ($msg as $m) {
            if ($m['role'] === 'system') $sys .= $m['content'] . "\n";
            else $turns[] = array('role' => $m['role'], 'content' => $m['content']);
        }
        $body = array('model' => $cfg['model'], 'max_tokens' => $max_tokens, 'messages' => $turns);
        if ($sys !== '') $body['system'] = $sys;
    } else {
        $hdr[] = 'Authorization: Bearer ' . $key;
        $body = array('model' => $cfg['model'], 'messages' => $msg,
                      'max_tokens' => $max_tokens, 'temperature' => 0.3);
    }

    $ch = curl_init($url);
    curl_setopt_array($ch, array(
        CURLOPT_POST           => true,
        CURLOPT_POSTFIELDS     => json_encode($body, JSON_UNESCAPED_UNICODE),
        CURLOPT_HTTPHEADER     => $hdr,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => $timeout,
        // ⚠ 검증을 끄지 않는다. 끄면 중간자가 프롬프트와 키를 본다.
        CURLOPT_SSL_VERIFYPEER => true,
        CURLOPT_SSL_VERIFYHOST => 2,
    ));
    $raw  = curl_exec($ch);
    $http = (int)curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $cerr = curl_error($ch);
    curl_close($ch);

    if ($raw === false) {
        return array('ok' => false, 'msg' => 'curl 실패: ' . $cerr
            . ' — 카페24에서 외부 HTTPS 가 막혀 있으면 이 단계에서 실패합니다.');
    }
    $d = json_decode($raw, true);
    if ($http !== 200 || !is_array($d)) {
        $em = '';
        if (is_array($d) && isset($d['error'])) {
            $em = is_array($d['error']) ? (isset($d['error']['message']) ? $d['error']['message'] : json_encode($d['error'])) : (string)$d['error'];
        }
        return array('ok' => false, 'http' => $http,
                     'msg' => 'HTTP ' . $http . ($em !== '' ? ' — ' . $em : ' — ' . mb_substr((string)$raw, 0, 300)));
    }

    /* 응답 파싱 — 공급자별로 위치가 다르다 */
    $text = ''; $ti = 0; $tc = 0; $to = 0;
    if ($cfg['provider'] === 'anthropic') {
        if (!empty($d['content'][0]['text'])) $text = $d['content'][0]['text'];
        $ti = (int)(isset($d['usage']['input_tokens']) ? $d['usage']['input_tokens'] : 0);
        $to = (int)(isset($d['usage']['output_tokens']) ? $d['usage']['output_tokens'] : 0);
        $tc = (int)(isset($d['usage']['cache_read_input_tokens']) ? $d['usage']['cache_read_input_tokens'] : 0);
    } else {
        if (isset($d['choices'][0]['message']['content'])) $text = (string)$d['choices'][0]['message']['content'];
        $u  = isset($d['usage']) ? $d['usage'] : array();
        $ti = (int)(isset($u['prompt_tokens']) ? $u['prompt_tokens'] : 0);
        $to = (int)(isset($u['completion_tokens']) ? $u['completion_tokens'] : 0);
        // DeepSeek 은 prompt_cache_hit_tokens 로 준다
        $tc = (int)(isset($u['prompt_cache_hit_tokens']) ? $u['prompt_cache_hit_tokens'] : 0);
        if ($tc > 0) $ti = max(0, $ti - $tc);      // 캐시 히트분은 따로 센다
    }
    if (trim($text) === '') {
        /* ★ "모델명을 확인하십시오" 만 말하면 안 된다.
         *
         *   실제로 5건 중 2건은 **같은 모델로 성공**하고 3건이 이 자리로 떨어졌다.
         *   그 상황에서 모델명을 의심하게 만드는 안내는 사람을 엉뚱한 데로 보낸다.
         *   HTTP 는 200 이고 content 만 비었다는 뜻이므로, 왜 비었는지를 응답이
         *   이미 들고 있다 — finish_reason 과 토큰 수다.
         *
         *   `length`            max_tokens 에서 잘렸다 → 상한을 올린다
         *   `content_filter`    공급자가 막았다 → 프롬프트를 손본다
         *   `stop` 인데 비었다  추론형 모델이 reasoning_content 에만 쓴 경우가 많다.
         *                       그 값은 **답이 아니라 사고 과정**이라 답변으로 쓰지 않는다.
         *                       상한을 올려 본문이 나오게 하는 것이 맞다.
         */
        $fin = '';
        if (isset($d['choices'][0]['finish_reason'])) $fin = (string)$d['choices'][0]['finish_reason'];
        elseif (isset($d['stop_reason']))            $fin = (string)$d['stop_reason'];

        $rz = 0;
        if (!empty($d['choices'][0]['message']['reasoning_content'])) {
            $rz = mb_strlen((string)$d['choices'][0]['message']['reasoning_content'], 'UTF-8');
        }

        $why = '응답 본문이 비었습니다';
        if ($fin === 'length')              $why = '응답이 최대 길이에서 잘렸습니다';
        elseif ($fin === 'content_filter')  $why = '공급자가 응답을 차단했습니다';
        elseif ($rz > 0)                    $why = '모델이 사고 과정만 쓰고 본문을 안 냈습니다';

        return array('ok' => false, 'msg' => $why
            . ' (HTTP 200 · finish_reason=' . ($fin !== '' ? $fin : '없음')
            . ' · 요청 max_tokens=' . (int)$max_tokens
            . ' · 출력 토큰 ' . $to
            . ($rz > 0 ? ' · 사고과정 ' . $rz . '자' : '')
            . ' · 모델 ' . $cfg['model'] . ')'
            . ($fin === 'length' || $rz > 0
               ? ' — max_tokens 를 올려야 합니다. 모델명 문제가 아닙니다.'
               : ''));
    }

    list($p_in, $p_cache, $p_out) = ex_llm_price($cfg['model']);
    $cost = ($ti / 1000 * $p_in) + ($tc / 1000 * $p_cache) + ($to / 1000 * $p_out);

    return array(
        'ok' => true, 'text' => trim($text), 'model' => $cfg['model'],
        'tok_in' => $ti, 'tok_cache' => $tc, 'tok_out' => $to,
        'cost' => round($cost, 4),
        // 원가 상한을 넘으면 화면이 경고한다. 막지는 않는다 —
        // 이미 호출은 끝났고, 막아야 할 곳은 다음 호출이다.
        'over_cap' => ($cfg['cost_cap'] > 0 && $cost > $cfg['cost_cap']),
        'cost_cap' => $cfg['cost_cap'],
    );
}
