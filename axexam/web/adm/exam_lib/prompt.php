<?php
/**
 * 답변 초안 프롬프트 조립.
 *
 * ── 왜 프롬프트를 파일로 빼는가 ────────────────────────────────────────────
 * 답변 품질은 모델보다 **프롬프트에 들어가는 재료**로 결정된다. 문제 본문·보기·정답·
 * 해설을 다 넣으면 값싼 모델도 정확한 답을 쓰고, 안 넣으면 비싼 모델도 헛소리를 한다.
 * 재료 조립이 곧 제품이므로 호출 코드(llm.php)와 분리해 여기만 고치면 되게 한다.
 *
 * ── 재료가 이미 DB 에 있다 ─────────────────────────────────────────────────
 * `ex_qna.pr_key` → `ex_problem` 한 행. 문제·지문·SQL·표·보기·정답·해설·태그가
 * 전부 있다. 문제를 정적 JS 로 뒀다면 서버가 이걸 읽을 방법이 없어서
 * 프롬프트에 문제 본문을 넣지 못한다 — DB 로 옮긴 실질적 이득 중 하나다.
 *
 * ── 정답을 프롬프트에 넣는다 ───────────────────────────────────────────────
 * 모델이 스스로 풀게 하면 틀린다. 우리는 정답과 해설을 **이미 알고 있으므로**
 * "왜 그 답인지 설명하라"는 문제로 바꿔 낸다. 이게 환각을 구조적으로 줄인다.
 *
 * ⚠ 초안은 관리자만 본다(`qa_draft`). 그래도 **틀린 초안은 검수 부담**이므로
 *   "모르면 모른다고 쓰라"를 시스템 프롬프트에 못 박는다.
 */
if (!defined('_GNUBOARD_')) exit;

/** 보기 배열 → "① …\n② …" */
function ex_pr_choices_text($choices_json)
{
    $c = json_decode((string)$choices_json, true);
    if (!is_array($c) || !$c) return '';
    $circ = array('①','②','③','④','⑤','⑥','⑦','⑧','⑨','⑩');
    $out = array();
    foreach ($c as $i => $t) {
        $out[] = (isset($circ[$i]) ? $circ[$i] : ($i + 1) . '.') . ' ' . trim((string)$t);
    }
    return implode("\n", $out);
}

/** 표 JSON → 마크다운 표 (모델이 표를 표로 읽게) */
function ex_pr_table_text($table_json)
{
    $t = json_decode((string)$table_json, true);
    if (!is_array($t) || empty($t['columns'])) return '';
    $out = '| ' . implode(' | ', $t['columns']) . " |\n";
    $out .= '| ' . implode(' | ', array_fill(0, count($t['columns']), '---')) . " |\n";
    foreach ((isset($t['rows']) ? $t['rows'] : array()) as $row) {
        $out .= '| ' . implode(' | ', array_map('strval', (array)$row)) . " |\n";
    }
    return $out;
}

/**
 * 문제 한 행 → 프롬프트에 넣을 텍스트 블록.
 */
function ex_prompt_problem($prob)
{
    if (!$prob) return '(질문에 연결된 문제가 없습니다 — 일반 질문입니다.)';

    $b = array();
    $b[] = '[문제] ' . (int)$prob['rd_no'] . '회 ' . (int)$prob['pr_no'] . '번'
         . ($prob['sj_name'] !== '' ? ' · ' . $prob['sj_name'] : '')
         . ($prob['difficulty'] !== '' ? ' · 난이도 ' . $prob['difficulty'] : '');
    $b[] = trim((string)$prob['question']);

    if (trim((string)$prob['passage']) !== '') $b[] = "[지문]\n" . trim($prob['passage']);
    if (trim((string)$prob['sql_text']) !== '') $b[] = "[SQL]\n" . trim($prob['sql_text']);
    $tbl = ex_pr_table_text($prob['table_json']);
    if ($tbl !== '') $b[] = "[표]\n" . $tbl;

    $ch = ex_pr_choices_text($prob['choices_json']);
    if ($ch !== '') $b[] = "[보기]\n" . $ch;

    /* ★ 정답을 준다. 모델이 다시 풀지 않게 하는 것이 이 설계의 핵심이다. */
    $ans = trim((string)$prob['answer_label']);
    if ($ans === '' && $prob['answer_index'] !== null) {
        $circ = array('①','②','③','④','⑤');
        $ai = (int)$prob['answer_index'];
        $ans = isset($circ[$ai]) ? $circ[$ai] : (string)($ai + 1);
    }
    if ($ans !== '') $b[] = '[정답] ' . $ans;
    if (trim((string)$prob['explanation']) !== '') $b[] = "[공식 해설]\n" . trim($prob['explanation']);

    $tags = json_decode((string)$prob['tags_json'], true);
    if (is_array($tags) && $tags) $b[] = '[개념] ' . implode(', ', $tags);

    return implode("\n\n", $b);
}

/**
 * 최종 메시지 배열. llm.php 의 ex_llm_call() 에 그대로 넘긴다.
 *
 * @param array $q     ex_qna 한 행 (+ pd_name)
 * @param array $prob  ex_problem 한 행 또는 null
 */
function ex_prompt_build($q, $prob)
{
    $pd_name = isset($q['pd_name']) ? $q['pd_name'] : $q['pd_id'];
    $is_report = (isset($q['kind']) && $q['kind'] === 'report');

    /* 시스템 프롬프트 — 지켜야 할 것을 짧고 단정하게. 길면 지키지 않는다. */
    $sys = "당신은 {$pd_name} 자격증 강사다. 수험생 질문에 답하는 초안을 쓴다.\n"
         . "\n"
         . "규칙:\n"
         . "1. 한국어로 쓴다. 존댓말로 쓴다.\n"
         . "2. [정답]과 [공식 해설]은 **확정된 사실**이다. 다시 풀지 말고 그것을 근거로 설명한다.\n"
         . "3. 질문이 [공식 해설]과 어긋나면, 해설을 부정하지 말고 **질문자가 어디서 헷갈렸는지** 짚는다.\n"
         . "4. 주어진 재료로 판단할 수 없으면 **모른다고 쓴다.** 추측해서 채우지 않는다.\n"
         . "5. 문제에 없는 문법·함수·버전을 끌어오지 않는다. 시험 범위를 넘기면 수험생이 불필요하게 불안해한다.\n"
         . "6. 분량은 3~6문장. 필요하면 짧은 불릿을 쓴다. 인사말·맺음말은 쓰지 않는다.\n"
         . "7. 마지막 줄에 한 문장으로 **핵심 정리**를 붙인다.\n";

    if ($is_report) {
        $sys .= "\n이 질문은 **문제 오류 신고**다. 다음을 판정해 먼저 밝힌다:\n"
              . "- 신고가 타당한가 (정답·보기·지문에 실제 오류가 있는가)\n"
              . "- 타당하지 않다면 왜 그렇게 보였는가\n"
              . "판정을 단정할 수 없으면 '검토 필요'라고 쓴다. 관리자가 판단한다.\n";
    }

    $user = ex_prompt_problem($prob) . "\n\n"
          . "────────\n"
          . '[질문자가 고른 보기] ';
    $chosen = isset($q['qa_chosen']) ? (int)$q['qa_chosen'] : -1;
    if ($chosen >= 0) {
        $circ = array('①','②','③','④','⑤','⑥','⑦','⑧','⑨','⑩');
        $user .= isset($circ[$chosen]) ? $circ[$chosen] : (string)($chosen + 1);
        /* 무엇을 골랐는지가 가장 중요한 재료다 — 왜 그 오답에 끌렸는지를
           집어주는 답변이 "해설 다시 읽기"보다 훨씬 도움이 된다. */
    } else {
        $user .= '(고르지 않음)';
    }
    $user .= "\n\n[질문]\n" . trim((string)$q['qa_question']);

    return array(
        array('role' => 'system', 'content' => $sys),
        array('role' => 'user',   'content' => $user),
    );
}

/**
 * 질문 1건 → 초안 생성 → ex_qna 에 기록.
 *
 * ★ 상태를 먼저 `drafting` 으로 바꾼다. 조건부 UPDATE 라 두 관리자가 동시에
 *   눌러도 한 번만 호출된다 — LLM 호출은 돈이 드니 중복이 곧 손해다.
 *
 * @return array ok · msg · cost
 */
function ex_draft_one($qa_id, $admin_id = '')
{
    $qa_id = (int)$qa_id;

    /* 잠금: pending|draft_ready 만 → drafting. affected=0 이면 남이 집었거나 이미 끝났다. */
    sql_query("update ex_qna set qa_status = 'drafting'
                where qa_id = $qa_id and qa_status in ('pending','draft_ready')", false);
    if (function_exists('sql_affected_rows_compat')) { $aff = sql_affected_rows_compat(); }
    else { $aff = function_exists('sql_affected_rows') ? sql_affected_rows() : 1; }
    if ($aff !== 1) {
        return array('ok' => false, 'msg' => '#' . $qa_id . ' 대상이 아닙니다(이미 처리됐거나 다른 관리자가 생성 중).');
    }

    $q = sql_fetch("select q.*, d.pd_name from ex_qna q
                     left join ex_product d on d.pd_id = q.pd_id
                    where q.qa_id = $qa_id");
    if (!$q) {
        return array('ok' => false, 'msg' => '#' . $qa_id . ' 질문을 찾을 수 없습니다.');
    }

    $prob = null;
    if ($q['pr_key'] !== '') {
        $prob = sql_fetch("select * from ex_problem
                            where pd_id = '" . sql_real_escape_string($q['pd_id']) . "'
                              and pr_key = '" . sql_real_escape_string($q['pr_key']) . "'");
    }

    $r = ex_llm_call($q['pd_id'], ex_prompt_build($q, $prob), 1200, 60);

    if (empty($r['ok'])) {
        /* 실패하면 원래 상태로 되돌린다. drafting 에 남겨두면 큐에서 영구히 사라진다 —
           운영자가 "왜 이 질문은 아무 일도 안 일어나지"로 헤매게 된다. */
        sql_query("update ex_qna set qa_status = 'pending' where qa_id = $qa_id", false);
        return array('ok' => false, 'msg' => '#' . $qa_id . ' ' . $r['msg']);
    }

    sql_query("update ex_qna set
                 qa_draft     = '" . sql_real_escape_string($r['text']) . "',
                 qa_model     = '" . sql_real_escape_string($r['model']) . "',
                 qa_tok_in    = " . (int)$r['tok_in'] . ",
                 qa_tok_cache = " . (int)$r['tok_cache'] . ",
                 qa_tok_out   = " . (int)$r['tok_out'] . ",
                 qa_cost      = " . (float)$r['cost'] . ",
                 qa_draft_at  = '" . G5_TIME_YMDHIS . "',
                 qa_status    = 'draft_ready'
               where qa_id = $qa_id", false);

    /* 감사 로그 — 누가 언제 얼마를 썼는가. 원가 추적의 유일한 근거다. */
    sql_query("insert into ex_log set mb_id = '" . sql_real_escape_string($admin_id) . "',
                 lo_act = 'draft', lo_ref = 'qna:$qa_id',
                 lo_ip = '" . sql_real_escape_string($_SERVER['REMOTE_ADDR']) . "',
                 created_at = '" . G5_TIME_YMDHIS . "'", false);

    return array('ok' => true, 'cost' => (float)$r['cost'], 'over_cap' => !empty($r['over_cap']),
                 'msg' => '#' . $qa_id . ' 초안 생성 (' . number_format($r['cost'], 4) . '원)');
}
