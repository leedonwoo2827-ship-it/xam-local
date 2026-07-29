<?php
if (!defined('_GNUBOARD_')) exit;

/**
 * problems.json → ex_problem upsert.
 *
 * ═══════════════════════════════════════════════════════════════════════════
 *  이 파일의 두 가지 불변식. 깨지면 데이터가 조용히 망가진다.
 * ═══════════════════════════════════════════════════════════════════════════
 *
 *  ① pr_id 는 절대 바뀌지 않는다.
 *     ex_attempt_item.pr_id 와 ex_wrong.pr_id 가 이걸 참조한다.
 *     그래서 **DELETE + INSERT 를 하지 않는다.** 기존 행은 UPDATE 만 한다.
 *     upsert 축은 UNIQUE (pd_id, pr_key) 이고 pr_key 는 build_check.py 가
 *     `bundle + '#' + number` 로 만든다(= check.html 의 keyOf()). 형식이 바뀌면
 *     같은 문제가 새 행으로 들어가 회원의 오답노트가 통째로 끊긴다.
 *
 *  ② edited_by 가 비어 있지 않은 행은 건드리지 않는다.
 *     관리자가 웹에서 고친 문제다. 재임포트가 이걸 덮으면 수정이 사라진다.
 *     되돌리려면 화면에서 "원본 복원"(edited_by 비우기)을 명시적으로 눌러야 한다.
 *
 *     ⚠ 그 대가: 웹 수정본은 02/ 원본과 어긋난 채로 남는다.
 *        주기적으로 02/ 로 역반영하지 않으면 언젠가 "원본 복원"이 낡은 내용을 되살린다.
 *
 * ═══════════════════════════════════════════════════════════════════════════
 *
 *  ON DUPLICATE KEY UPDATE 대신 "먼저 SELECT 해서 분류 → INSERT 또는 UPDATE" 로 짰다.
 *  이유: 신규/갱신/건너뜀(웹수정)/변경없음 을 정확히 세어 보고해야 하는데
 *        affected_rows 는 '건너뜀'과 '변경없음'을 구분하지 못한다(둘 다 0).
 *        임포트 리포트의 신뢰성이 이 구분에 달려 있다.
 */

/** 문자열 이스케이프 — sql_escape_string() 은 사실상 addslashes() 라 쓰지 않는다. */
function ex_s($v) { return sql_real_escape_string((string)$v); }

/** JSON 컬럼용. 빈 값이면 SQL NULL. */
function ex_json_col($v) {
    if ($v === null || $v === '' || $v === array()) return 'NULL';
    return "'" . sql_real_escape_string(json_encode($v, JSON_UNESCAPED_UNICODE)) . "'";
}

/** TEXT 컬럼용. 빈 문자열은 NULL 로 두지 않고 그대로 저장한다(NOT NULL 컬럼 대비). */
function ex_txt_col($v) {
    return "'" . sql_real_escape_string((string)$v) . "'";
}

/** NULL 허용 TEXT. */
function ex_txt_null($v) {
    $v = (string)$v;
    if ($v === '') return 'NULL';
    return "'" . sql_real_escape_string($v) . "'";
}

/**
 * pr_key 형식 검증.
 * build_check.py 가 만드는 형식만 통과시킨다 — 'm01-1#7'.
 * 임의 문자열이 UNIQUE 축에 들어가면 나중에 되돌릴 수 없다.
 */
function ex_valid_pr_key($k) {
    return (bool)preg_match('/^m\d{2}-\d{1,2}#\d{1,3}$/', (string)$k);
}

/**
 * 임포트 본체.
 *
 * @param array  $doc      problems.json 을 json_decode(true) 한 것
 * @param string $admin_id 실행한 관리자 mb_id (로그용)
 * @return array 리포트
 */
function ex_import_problems($doc, $admin_id = '') {
    $rep = array(
        'pd_id' => '', 'total' => 0,
        'new' => 0, 'upd' => 0, 'skip_edited' => 0, 'skip_same' => 0, 'fail' => 0,
        'rounds' => 0,
        'errors' => array(),        // 치명적 — 임포트 중단
        'warns'  => array(),        // 행 단위 실패
        'edited_keys' => array(),   // 건너뛴 웹 수정본 목록
    );

    // ── 문서 레벨 검증 ──────────────────────────────────────────────────
    if (!is_array($doc)) {
        $rep['errors'][] = 'JSON 파싱 실패 — 파일이 problems.json 이 맞는지 확인하십시오.';
        return $rep;
    }
    $pd_id = isset($doc['pd_id']) ? trim((string)$doc['pd_id']) : '';
    if ($pd_id === '' || !preg_match('/^[a-z0-9\-]{1,20}$/', $pd_id)) {
        $rep['errors'][] = "pd_id 가 없거나 형식이 잘못됐습니다: '".htmlspecialchars($pd_id)."'";
        return $rep;
    }
    $rep['pd_id'] = $pd_id;

    $probs = isset($doc['problems']) && is_array($doc['problems']) ? $doc['problems'] : array();
    if (!$probs) {
        $rep['errors'][] = 'problems 배열이 비어 있습니다.';
        return $rep;
    }
    $rep['total'] = count($probs);

    // 품목이 등록돼 있어야 한다. 없으면 FK 는 아니지만 화면에서 안 보인다.
    $pd = sql_fetch("select pd_id from ex_product where pd_id = '".ex_s($pd_id)."'");
    if (!$pd) {
        $rep['errors'][] = "ex_product 에 pd_id='".htmlspecialchars($pd_id)."' 가 없습니다. "
                         . "master.sql 을 먼저 실행하십시오.";
        return $rep;
    }

    // ── 기존 행을 한 번에 읽어 분류 기준을 만든다 ───────────────────────
    $exist = array();   // pr_key => array(pr_id, pr_hash, edited_by)
    $res = sql_query("select pr_id, pr_key, pr_hash, edited_by
                        from ex_problem where pd_id = '".ex_s($pd_id)."'");
    while ($r = sql_fetch_array($res)) {
        $exist[$r['pr_key']] = $r;
    }

    $now  = G5_TIME_YMDHIS;
    $seen_rounds = array();

    foreach ($probs as $p) {
        $pr_key = isset($p['pr_key']) ? (string)$p['pr_key'] : '';
        if (!ex_valid_pr_key($pr_key)) {
            $rep['fail']++;
            $rep['warns'][] = "pr_key 형식 오류로 건너뜀: '".htmlspecialchars(mb_substr($pr_key, 0, 40))."'";
            continue;
        }

        $rd_no = (int)(isset($p['rd_no']) ? $p['rd_no'] : 0);
        $pr_no = (int)(isset($p['pr_no']) ? $p['pr_no'] : 0);
        if ($rd_no <= 0 || $pr_no <= 0) {
            $rep['fail']++;
            $rep['warns'][] = "$pr_key : rd_no/pr_no 가 유효하지 않습니다.";
            continue;
        }
        $seen_rounds[$rd_no] = isset($seen_rounds[$rd_no]) ? $seen_rounds[$rd_no] + 1 : 1;

        $hash = isset($p['pr_hash']) ? (string)$p['pr_hash'] : '';

        // ── 분류 ────────────────────────────────────────────────────────
        if (isset($exist[$pr_key])) {
            $cur = $exist[$pr_key];
            if ($cur['edited_by'] !== '') {          // ② 웹 수정본 보호
                $rep['skip_edited']++;
                $rep['edited_keys'][] = $pr_key;
                continue;
            }
            if ($hash !== '' && $hash === $cur['pr_hash']) {   // 내용 동일
                $rep['skip_same']++;
                continue;
            }
            $mode = 'update';
        } else {
            $mode = 'insert';
        }

        // ── 컬럼 값 ─────────────────────────────────────────────────────
        $cols = array(
            'rd_no'        => (int)$rd_no,
            'pr_key'       => "'".ex_s($pr_key)."'",
            'bundle'       => "'".ex_s(isset($p['bundle']) ? $p['bundle'] : '')."'",
            'pr_no'        => (int)$pr_no,
            'src_id'       => "'".ex_s(isset($p['src_id']) ? $p['src_id'] : '')."'",
            'src_from'     => "'".ex_s(isset($p['src_from']) ? $p['src_from'] : '')."'",
            'sj_no'        => (int)(isset($p['sj_no']) ? $p['sj_no'] : 0),
            'sj_name'      => "'".ex_s(isset($p['sj_name']) ? $p['sj_name'] : '')."'",
            'difficulty'   => "'".ex_s(isset($p['difficulty']) ? $p['difficulty'] : '')."'",
            'question'     => ex_txt_col(isset($p['question']) ? $p['question'] : ''),
            'passage'      => ex_txt_null(isset($p['passage']) ? $p['passage'] : ''),
            'sql_text'     => ex_txt_null(isset($p['sql_text']) ? $p['sql_text'] : ''),
            'table_json'   => ex_json_col(isset($p['table_json'])   ? $p['table_json']   : null),
            'figures_json' => ex_json_col(isset($p['figures_json']) ? $p['figures_json'] : null),
            'choices_json' => ex_json_col(isset($p['choices_json']) ? $p['choices_json'] : array()),
            'n_choices'    => (int)(isset($p['n_choices']) ? $p['n_choices'] : 4),
            'answer_index' => (isset($p['answer_index']) && $p['answer_index'] !== null)
                                ? (int)$p['answer_index'] : 'NULL',
            'answer_label' => "'".ex_s(isset($p['answer_label']) ? $p['answer_label'] : '')."'",
            'explanation'  => ex_txt_null(isset($p['explanation']) ? $p['explanation'] : ''),
            'tags_json'    => ex_json_col(isset($p['tags_json']) ? $p['tags_json'] : null),
            'has_figure'   => !empty($p['has_figure'])   ? 1 : 0,
            'has_sql'      => !empty($p['has_sql'])      ? 1 : 0,
            'has_table'    => !empty($p['has_table'])    ? 1 : 0,
            'verified'     => !empty($p['verified'])     ? 1 : 0,
            'reviewed'     => !empty($p['reviewed'])     ? 1 : 0,
            'needs_review' => !empty($p['needs_review']) ? 1 : 0,
            'pr_hash'      => "'".ex_s($hash)."'",
            'updated_at'   => "'".ex_s($now)."'",
        );
        // choices_json 은 NOT NULL 이다 — 빈 배열이 NULL 로 가면 안 된다
        if ($cols['choices_json'] === 'NULL') $cols['choices_json'] = "'[]'";

        // ⚠ pr_open 은 건드리지 않는다.
        //    오류 신고로 관리자가 숨긴 문제를 재임포트가 되살리면 안 된다.
        //    edited_by / edited_at 도 마찬가지로 임포트가 쓰지 않는다.

        if ($mode === 'insert') {
            $names = array_keys($cols);
            $vals  = array_values($cols);
            $sql = "insert into ex_problem (pd_id, ".implode(', ', $names).")
                         values ('".ex_s($pd_id)."', ".implode(', ', $vals).")";
        } else {
            $sets = array();
            foreach ($cols as $k => $v) {
                if ($k === 'pr_key') continue;   // upsert 축은 바꾸지 않는다
                $sets[] = "$k = $v";
            }
            $sql = "update ex_problem set ".implode(', ', $sets)."
                     where pd_id = '".ex_s($pd_id)."' and pr_key = '".ex_s($pr_key)."'";
        }

        // G5_DISPLAY_SQL_ERROR 를 끄고(false) 실패를 우리가 센다 —
        // 300건 중 1건이 죽었다고 화면 전체가 날아가면 안 된다.
        $ok = sql_query($sql, false);
        if (!$ok) {
            $rep['fail']++;
            $rep['warns'][] = "$pr_key : DB 오류 — ".sql_error_info();
            continue;
        }
        if ($mode === 'insert') $rep['new']++; else $rep['upd']++;
    }

    // ── 회차 갱신 ───────────────────────────────────────────────────────
    $labels = array();
    if (isset($doc['rounds']) && is_array($doc['rounds'])) {
        foreach ($doc['rounds'] as $r) {
            if (isset($r['rd_no'])) $labels[(int)$r['rd_no']] = (string)$r['rd_label'];
        }
    }
    foreach ($seen_rounds as $rd_no => $cnt) {
        $label = isset($labels[$rd_no]) ? $labels[$rd_no] : ($rd_no.'회');
        // rd_free / rd_open 은 운영자가 화면에서 바꾸는 값이라 임포트가 덮지 않는다.
        $sql = "insert into ex_round (pd_id, rd_no, rd_label, rd_count)
                     values ('".ex_s($pd_id)."', ".(int)$rd_no.", '".ex_s($label)."', ".(int)$cnt.")
                on duplicate key update rd_label = values(rd_label), rd_count = values(rd_count)";
        if (sql_query($sql, false)) $rep['rounds']++;
        else $rep['warns'][] = "회차 $rd_no 갱신 실패 — ".sql_error_info();
    }

    return $rep;
}

/**
 * "원본 복원" — edited_by 를 비워 다음 임포트가 다시 덮도록 한다.
 * 이것만으로는 내용이 안 바뀐다. 비운 뒤 problems.json 을 다시 임포트해야 한다.
 */
function ex_problem_unlock($pd_id, $pr_key) {
    sql_query("update ex_problem
                  set edited_by = '', edited_at = null
                where pd_id = '".ex_s($pd_id)."' and pr_key = '".ex_s($pr_key)."'", false);
    return sql_affected_rows_compat();
}

/**
 * sql_affected_rows() 래퍼 존재 여부가 확인되지 않았다(GNUBOARD-FACTS §14-13).
 * 있으면 쓰고, 없으면 mysqli 를 직접 호출한다.
 * ⚠ 크레딧 차감(S6)이 이 함수의 정확성에 통째로 의존한다.
 */
function sql_affected_rows_compat() {
    global $g5;
    if (function_exists('sql_affected_rows')) return (int)sql_affected_rows();
    return (int)mysqli_affected_rows($g5['connect_db']);
}
