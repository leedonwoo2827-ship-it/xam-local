<?php
/**
 * 과목게시판 ↔ `ex_qna` 다리.
 *
 * ── 왜 필요한가 ────────────────────────────────────────────────────────────
 * 질문은 **그누보드 과목게시판**으로 들어온다(`check.js` 의 [질문하기] 가 게시판
 * 글쓰기로 보낸다). 그런데 답변 초안·검수·승인 흐름은 `ex_qna` 위에 있다.
 * 둘이 이어지지 않아서, 초안 기능이 다 만들어져 있는데도 **큐가 영원히 비어 있었다.**
 *
 * `ex_qna` 는 처음부터 이 다리를 예정했다 — `bo_table` · `wr_id` 컬럼이 있고,
 * 질문 검수 목록은 그 두 값이 있으면 `게시판 글` 링크를 이미 띄운다.
 *
 * ── 두 방향 ────────────────────────────────────────────────────────────────
 *   ex_qna_sync_board()   게시판 원글  →  ex_qna (pending)      [가져오기]
 *   ex_answer_to_board()  확정 답변    →  게시판 댓글            [승인]
 *
 * ── ★ g5_write_* 컬럼을 추측하지 않는다 ────────────────────────────────────
 * 여기가 **회원 데이터를 쓰는 자리**다. 그누보드 표준 컬럼이지만 버전·스킨·플러그인에
 * 따라 다를 수 있고, 틀리면 INSERT 가 실패한다. 게다가 `sql_query(..., false)` 는
 * 오류를 삼켜서 조용히 실패한다 — 오늘 `wr_category` 로 정확히 그 사고를 겪었다
 * (없는 컬럼을 읽어 목록이 항상 비어 보였다).
 *
 * → `SHOW COLUMNS` 로 **실제 컬럼을 읽어** 교집합만 INSERT 한다. 없는 컬럼은 넣지
 *   않고 DB 기본값에 맡긴다. 그리고 실패는 반드시 문자열로 되돌려 화면에 띄운다.
 *
 * ── 원가 ───────────────────────────────────────────────────────────────────
 * 초안 1건 = LLM 호출 1건 = 돈이다. 그래서 이 파일은 초안을 만들지 않는다 —
 * `ex_draft_one()`(exam_lib/prompt.php)을 부르는 것은 화면 쪽이고, 화면이 건수와
 * 예상 원가를 먼저 보여주고 확인을 받는다.
 */
if (!defined('_GNUBOARD_')) exit;

/**
 * 답변 댓글을 HTML 로 쓸지 — **false 다. 실측으로 정했다.**
 *
 * ── 실측 (2026-08-05) ──────────────────────────────────────────────────────
 * `wr_option = 'html2'` 로 `<p><b>…</b></p>` 를 넣어 봤더니 게시판이 태그를
 * **글자 그대로** 보여줬다:
 *
 *     <p><b>[관리자 답변]</b></p>
 *     <p>신고가 타당합니다. 해당 문제는 <b>복수 정답 오류</b>에 …
 *
 * → 그누보드 5.6.34 의 **댓글 렌더는 `wr_option` 의 html 플래그를 보지 않는다.**
 *   게시판 설정의 'HTML 쓰기 권한 = 10' 은 **글(원문)** 에만 걸리는 권한이고,
 *   댓글 출력 경로는 그것과 별개다. 원문과 댓글을 같은 규칙으로 가정하면 안 된다.
 *
 * ★ 그래서 상수로 꺼내 두었다. 추측을 코드에 묻어두지 않았기 때문에 되돌리는 데
 *   한 줄과 [승인] 한 번이면 됐다 — 이런 자리는 앞으로도 상수로 둔다.
 *
 * ★ 평문이 손해가 아니다. `ex_md_plain()` 이 `**굵게**`→굵게, `- `→`· ` 로 정리하고
 *   줄바꿈은 그누보드가 알아서 `<br>` 로 만든다. 강조만 사라지고 문장은 그대로 읽힌다.
 *   HTML 로 쓸 때 딸려 오던 `&quot;` 같은 엔티티 노출도 함께 없어진다.
 *
 * 굵게가 꼭 필요해지면 스킨(`skin/board/basic-xam/view_comment.skin.php`)에서
 * 내용을 그릴 때 `ex_md_html()` 을 통과시키는 쪽이 맞다 — 그건 우리 파일이라 확인 가능하다.
 */
if (!defined('EX_BOARD_HTML')) define('EX_BOARD_HTML', false);
if (!defined('EX_BOARD_HTML_OPT')) define('EX_BOARD_HTML_OPT', 'html2');

/** 문제집 → 게시판 테이블명.
 *
 * ⚠ 이 규칙은 세 곳에 있다: 여기 · `exam/api/board.php` · `adm/exam_board_sync.php`.
 *   한 곳만 고치면 게시판을 못 찾아 **에러 없이 빈 목록**이 된다. 셋을 같이 고친다.
 *   (공유 파일로 빼지 않은 이유: adm 과 exam 이 서로를 include 하지 않는 구조다.) */
function exbq_bo($pd_id)
{
    $t = preg_replace('/[^a-z0-9_]/', '_', strtolower((string)$pd_id));
    return substr($t . '_sj', 0, 20);
}

function exbq_s($v) { return sql_real_escape_string((string)$v); }

/** 게시판 글 테이블명 (`g5_write_bigdata_sj`). */
function exbq_wt($bo)
{
    global $g5;
    return $g5['write_prefix'] . preg_replace('/[^a-z0-9_]/', '', (string)$bo);
}

/** 그 테이블에 실제로 있는 컬럼 이름들. 요청 1회당 한 번만 읽는다. */
function exbq_cols($table)
{
    static $cache = array();
    if (isset($cache[$table])) return $cache[$table];

    $cols = array();
    $res = sql_query("show columns from `" . $table . "`", false);
    while ($res && $r = sql_fetch_array($res)) {
        $cols[$r['Field']] = true;
    }
    $cache[$table] = $cols;
    return $cols;
}

/** 게시판이 실제로 있는가. 없으면 가져오기가 조용히 0건이 되면 안 된다. */
function exbq_board_exists($bo)
{
    global $g5;
    $b = sql_fetch("select bo_table from " . $g5['board_table'] . "
                     where bo_table = '" . exbq_s($bo) . "'");
    if (!$b) return false;
    return count(exbq_cols(exbq_wt($bo))) > 0;
}

/**
 * `ex_qna.qa_reply_wr_id` 를 보장한다 — 우리가 쓴 **답변 댓글의 wr_id**.
 *
 * 왜 컬럼을 더하는가: 이게 없으면 재승인(오타 수정)이 게시판에 반영되지 못한다.
 * 첫 승인에만 댓글을 쓰고 그 뒤 수정은 게시판에 안 나가는 것은, 이 프로젝트가
 * 내내 지켜온 "**수정이 쉬워야 한다**" 와 정면으로 어긋난다.
 *
 * ADD COLUMN IF NOT EXISTS 는 MariaDB 10.0+ 문법이고 이 서버는 10.6+ 다
 * (schema.sql §콜레이션 주석). 여러 번 돌려도 안전하다.
 * POST 처리에서만 부른다 — 조회마다 ALTER 를 던질 이유가 없다.
 */
function exbq_ensure_schema()
{
    static $done = false;
    if ($done) return;
    $done = true;
    sql_query("alter table ex_qna
                 add column if not exists qa_reply_wr_id int unsigned not null default 0", false);
}

/**
 * 제목·본문에서 `1회 61번` 같은 표식을 찾아 `pr_key` 로 바꾼다.
 *
 * ★ 초안 품질이 여기서 갈린다. `ex_draft_one()` 은 `pr_key` 로 문항(발문·보기·정답·
 *   해설)을 찾아 프롬프트에 넣는다. 못 찾으면 모델이 문제를 모른 채 일반론을 쓴다.
 *   그래서 자동 연결을 최대한 시도하고, 실패하면 빈 문자열로 둔다(초안은 그래도 나온다 —
 *   과목만으로).
 *
 * 회차·번호로 찾는 이유: 사람이 제목에 적는 것은 `pr_key`(m01-7#61)가 아니라
 * `1회 61번` 이다. 그 표기를 그대로 받는다.
 */
function exbq_guess_prkey($pd_id, $text)
{
    $s = (string)$text;

    // ① 회차·번호 — '1회 61번' · '[1회 61번]' · '1 회 61 번' · '1회차 61번'
    if (preg_match('/(\d{1,3})\s*회(?:차)?\s*(\d{1,3})\s*번/u', $s, $m)) {
        $r = sql_fetch("select pr_key from ex_problem
                         where pd_id = '" . exbq_s($pd_id) . "'
                           and rd_no = " . (int)$m[1] . " and pr_no = " . (int)$m[2] . "
                         limit 1");
        if ($r) return $r['pr_key'];
    }

    // ② pr_key 를 그대로 적은 경우 — m01-7#61
    if (preg_match('/\bm\d{2}-\d{1,2}#\d{1,3}\b/u', $s, $m)) {
        $r = sql_fetch("select pr_key from ex_problem
                         where pd_id = '" . exbq_s($pd_id) . "'
                           and pr_key = '" . exbq_s($m[0]) . "' limit 1");
        if ($r) return $r['pr_key'];
    }

    return '';
}

/** 말머리(과목명) → sj_no. 말머리는 exam_board_sync.php 가 과목명으로 맞춰 둔다. */
function exbq_sj_no($pd_id, $ca_name)
{
    $ca = trim((string)$ca_name);
    if ($ca === '') return 0;
    $r = sql_fetch("select sj_no from ex_problem
                     where pd_id = '" . exbq_s($pd_id) . "'
                       and sj_name = '" . exbq_s($ca) . "' limit 1");
    return $r ? (int)$r['sj_no'] : 0;
}

/**
 * 게시판 원글 하나 → `ex_qna` 행 하나. 이미 있으면 그 qa_id 를 돌려준다(멱등).
 *
 * `kind` 판정: 제목에 '오류'/'신고'/'틀린' 이 있으면 `report` 다. 오류 신고는
 * 질문권을 안 쓰고(`api/qna.php` 도 그렇게 한다) 검수 우선순위도 다르다.
 *
 * 차감은 **하지 않는다**(cost_units = 0 · qa_credit_ok = 1). 게시판 글쓰기는
 * 그누보드가 처리하므로 우리 코드를 지나지 않는다 — 나중에 걷을 수 없는 돈을
 * 걷은 것처럼 기록하면 회계가 틀어진다. 유료화는 회원 폼(`api/qna.php`) 경로다.
 */
function exbq_pull_one($pd_id, $bo, $wr_id, $by = '')
{
    $wr_id = (int)$wr_id;
    $wt    = exbq_wt($bo);

    $has = sql_fetch("select qa_id from ex_qna
                       where bo_table = '" . exbq_s($bo) . "' and wr_id = " . $wr_id . " limit 1");
    if ($has) return array('ok' => true, 'qa_id' => (int)$has['qa_id'], 'new' => false);

    $cols = exbq_cols($wt);
    if (!$cols) return array('ok' => false, 'msg' => "게시판 테이블을 읽지 못했습니다: $wt");

    $sel = array('wr_id', 'wr_subject', 'wr_content', 'mb_id', 'wr_name', 'wr_datetime');
    if (isset($cols['ca_name'])) $sel[] = 'ca_name';
    $p = sql_fetch("select " . implode(', ', $sel) . " from `$wt`
                     where wr_id = $wr_id and wr_is_comment = 0");
    if (!$p) return array('ok' => false, 'msg' => "#$wr_id 원글을 찾을 수 없습니다.");

    /* 질문 본문 = 제목 + 본문. 제목에 핵심이 들어가는 경우가 많고(회차·번호도 거기 있다),
       초안 프롬프트가 둘을 같이 봐야 맥락이 산다. */
    $subject = (string)$p['wr_subject'];
    $content = trim(strip_tags(str_replace(array('<br>', '<br/>', '<br />', '</p>'), "\n",
                                           (string)$p['wr_content'])));
    $content = html_entity_decode($content, ENT_QUOTES, 'UTF-8');
    $question = $subject . "\n\n" . $content;

    $ca     = isset($p['ca_name']) ? $p['ca_name'] : '';
    $sj_no  = exbq_sj_no($pd_id, $ca);
    $pr_key = exbq_guess_prkey($pd_id, $subject . "\n" . $content);
    $kind   = preg_match('/오류|신고|틀린|잘못/u', $subject) ? 'report' : 'qna';

    sql_query("insert into ex_qna
                 (mb_id, pd_id, kind, pr_key, sj_no, bo_table, wr_id,
                  qa_question, qa_chosen, qa_status,
                  cost_units, qa_credit_ok, qa_public, created_at)
               values
                 ('" . exbq_s($p['mb_id']) . "', '" . exbq_s($pd_id) . "', '" . exbq_s($kind) . "',
                  '" . exbq_s($pr_key) . "', " . (int)$sj_no . ",
                  '" . exbq_s($bo) . "', " . $wr_id . ",
                  '" . exbq_s($question) . "', -1, 'pending',
                  0, 1, 1,
                  '" . exbq_s($p['wr_datetime']) . "')", false);

    $qa_id = (int)sql_insert_id();
    if (!$qa_id) {
        return array('ok' => false, 'msg' => "#$wr_id ex_qna 등록 실패 — " . sql_error_info());
    }

    sql_query("insert into ex_log set mb_id = '" . exbq_s($by) . "',
                 lo_act = 'qna', lo_ref = 'pull:$bo:$wr_id',
                 lo_ip = '" . exbq_s(isset($_SERVER['REMOTE_ADDR']) ? $_SERVER['REMOTE_ADDR'] : '') . "',
                 created_at = '" . G5_TIME_YMDHIS . "'", false);

    return array('ok' => true, 'qa_id' => $qa_id, 'new' => true,
                 'pr_key' => $pr_key, 'sj_no' => $sj_no, 'kind' => $kind);
}

/**
 * 아직 `ex_qna` 에 없는 게시판 원글을 전부 가져온다.
 *
 * `$limit` 은 한 번에 처리할 최대 건수. LLM 을 부르지 않으므로(INSERT 뿐) 넉넉히 둘 수
 * 있지만, 첫 도입 때 수천 건이 있을 수도 있으니 상한을 둔다.
 * ★ 상한에 걸려 남은 것이 있으면 **그 사실을 돌려준다.** 조용히 잘리면 "다 가져왔다"
 *   고 믿게 된다.
 */
function exbq_pull_board($pd_id, $by = '', $limit = 200)
{
    exbq_ensure_schema();

    $bo = exbq_bo($pd_id);
    $wt = exbq_wt($bo);

    if (!exbq_board_exists($bo)) {
        return array('ok' => false, 'bo' => $bo,
                     'msg' => "과목게시판이 없습니다 — bo_table = $bo. "
                            . "그누보드 관리자 → 게시판 관리에서 먼저 만드십시오.");
    }

    /* 링크되지 않은 원글만. not exists 로 거른다 —
       ex_qna 를 다 읽어 PHP 에서 비교하면 글이 늘수록 메모리가 커진다. */
    $boq = exbq_s($bo);
    $ids = array();
    $res = sql_query("select w.wr_id from `$wt` w
                       where w.wr_is_comment = 0
                         and not exists (select 1 from ex_qna q
                                          where q.bo_table = '$boq' and q.wr_id = w.wr_id)
                       order by w.wr_id asc
                       limit " . ((int)$limit + 1), false);
    if ($res === false) {
        return array('ok' => false, 'bo' => $bo,
                     'msg' => "게시판 글을 읽지 못했습니다 ($wt) — " . sql_error_info());
    }
    while ($r = sql_fetch_array($res)) $ids[] = (int)$r['wr_id'];

    $more = 0;
    if (count($ids) > $limit) { $ids = array_slice($ids, 0, $limit); $more = 1; }

    $new = 0; $fail = array();
    foreach ($ids as $wr_id) {
        $r = exbq_pull_one($pd_id, $bo, $wr_id, $by);
        if (!empty($r['ok'])) { if (!empty($r['new'])) $new++; }
        else                  { $fail[] = $r['msg']; }
    }

    return array('ok' => true, 'bo' => $bo, 'new' => $new,
                 'fail' => $fail, 'more' => $more, 'scanned' => count($ids));
}

/**
 * 확정 답변 → 게시판 **댓글**.
 *
 * ★ 답변글(`wr_reply`)이 아니라 댓글(`wr_is_comment = 1`)로 쓴다.
 *   답변글은 `wr_num`·`wr_reply` 문자열 규칙을 정확히 흉내내야 하고, 틀리면 목록
 *   정렬이 조용히 깨진다. 댓글은 부모의 `wr_num` 을 그대로 쓰고 `wr_parent` 만
 *   맞추면 되므로 실패할 자리가 적다.
 *
 * 재승인(수정)이면 **기존 댓글을 갱신**한다 — `qa_reply_wr_id` 를 들고 있어서 가능하다.
 * 새로 달면 같은 질문에 답이 두 개 붙는다.
 */
function exbq_answer_to_board($qa_id, $by = '')
{
    global $g5;
    exbq_ensure_schema();

    $qa_id = (int)$qa_id;
    $q = sql_fetch("select qa_id, bo_table, wr_id, qa_reply_wr_id, qa_answer, qa_status
                      from ex_qna where qa_id = $qa_id");
    if (!$q)                                return array('ok' => false, 'msg' => '질문을 찾을 수 없습니다.');
    if ($q['bo_table'] === '' || !$q['wr_id'])
        return array('ok' => false, 'skip' => true, 'msg' => '게시판에서 온 질문이 아닙니다.');
    if ($q['qa_status'] !== 'approved')     return array('ok' => false, 'msg' => '승인된 답변만 게시판에 씁니다.');

    $answer = trim((string)$q['qa_answer']);
    if ($answer === '')                     return array('ok' => false, 'msg' => '답변이 비어 있습니다.');

    $bo = $q['bo_table'];
    $wt = exbq_wt($bo);
    $cols = exbq_cols($wt);
    if (!$cols) return array('ok' => false, 'msg' => "게시판 테이블을 읽지 못했습니다: $wt");

    $parent = sql_fetch("select wr_id, wr_num from `$wt`
                          where wr_id = " . (int)$q['wr_id'] . " and wr_is_comment = 0");
    if (!$parent) return array('ok' => false, 'msg' => '원글이 삭제된 것 같습니다.');

    /* 답변 앞에 표식을 붙인다. 게시판만 보는 사람이 "관리자 답변"임을 알아야 하고,
       회원끼리의 댓글과 구분돼야 한다.

       ★ 마크다운 기호를 떼어 평문으로 만든다. 초안은 `**굵게**` 를 쓰는데, 게시판
         댓글은 HTML 허용 여부를 그누보드 코어가 정하고 그 코어는 우리 저장소에 없다.
         추측으로 html 을 켜면 태그가 글자로 보이거나 의도보다 넓게 허용된다 —
         둘 다 나쁘다. 평문으로 정리하면 어느 쪽이든 읽힌다. (exam/lib/md.php) */
    require_once G5_PATH . '/exam/lib/md.php';
    if (EX_BOARD_HTML) {
        // 게시판 설정의 'HTML 쓰기 권한' 이 10(최고관리자)이라 회원에게는 열리지 않는다.
        $body = '<p><b>[관리자 답변]</b></p>' . "\n" . ex_md_html($answer);
        $opt  = EX_BOARD_HTML_OPT;
    } else {
        $body = "[관리자 답변]\n\n" . ex_md_plain($answer);
        $opt  = '';
    }

    /* ── 이미 쓴 댓글이 있으면 내용만 갈아 끼운다 ── */
    $rid = (int)$q['qa_reply_wr_id'];
    if ($rid > 0) {
        $exists = sql_fetch("select wr_id from `$wt` where wr_id = $rid and wr_is_comment = 1");
        if ($exists) {
            /* ★ wr_option 도 같이 갱신한다. 안 하면 EX_BOARD_HTML 을 바꾼 뒤 재승인해도
                 옛 옵션이 남아 태그가 글자로 보인다(또는 반대로 평문에 html 옵션이
                 남는다). 되돌리기가 "상수 한 줄 + 승인 다시" 로 끝나야 한다. */
            $set_u = "wr_content = '" . exbq_s($body) . "'";
            if (isset($cols['wr_option'])) $set_u .= ", wr_option = '" . exbq_s($opt) . "'";
            sql_query("update `$wt` set $set_u
                        where wr_id = $rid and wr_is_comment = 1", false);
            return array('ok' => true, 'wr_id' => $rid, 'updated' => true);
        }
        // 댓글이 지워졌다 → 아래에서 새로 쓴다
    }

    /* ── 새 댓글 ──
     * 그누보드 표준 컬럼값을 만들어 두고, **실제로 있는 컬럼만** 골라 INSERT 한다.
     * 없는 컬럼은 DB 기본값에 맡긴다(대부분 NOT NULL DEFAULT '').
     */
    $now  = G5_TIME_YMDHIS;
    $ip   = isset($_SERVER['REMOTE_ADDR']) ? $_SERVER['REMOTE_ADDR'] : '';
    $name = isset($GLOBALS['member']['mb_nick']) && $GLOBALS['member']['mb_nick'] !== ''
          ? $GLOBALS['member']['mb_nick'] : '관리자';

    $vals = array(
        'wr_num'           => (int)$parent['wr_num'],   // 부모와 같아야 같이 묶여 정렬된다
        'wr_reply'         => '',
        'wr_parent'        => (int)$parent['wr_id'],
        'wr_is_comment'    => 1,
        'wr_comment'       => 0,
        'wr_comment_reply' => '',
        'ca_name'          => '',
        'wr_option'        => $opt,      // 'html2' 또는 '' — 위 EX_BOARD_HTML 참조
        'wr_subject'       => '',
        'wr_content'       => $body,
        'wr_link1'         => '',
        'wr_link2'         => '',
        'wr_link1_hit'     => 0,
        'wr_link2_hit'     => 0,
        'wr_hit'           => 0,
        'wr_good'          => 0,
        'wr_nogood'        => 0,
        'mb_id'            => (string)$by,
        'wr_password'      => '',
        'wr_name'          => $name,
        'wr_email'         => '',
        'wr_homepage'      => '',
        'wr_datetime'      => $now,
        'wr_last'          => '',
        'wr_ip'            => $ip,
        'wr_facebook_user' => '',
        'wr_twitter_user'  => '',
    );
    for ($i = 1; $i <= 10; $i++) $vals['wr_' . $i] = '';

    $set = array();
    foreach ($vals as $k => $v) {
        if (!isset($cols[$k])) continue;                       // 없는 컬럼은 건너뛴다
        $set[] = "`$k` = " . (is_int($v) ? $v : "'" . exbq_s($v) . "'");
    }
    if (!$set) return array('ok' => false, 'msg' => '쓸 수 있는 컬럼이 없습니다 — 테이블 구조를 확인하십시오.');

    sql_query("insert into `$wt` set " . implode(', ', $set), false);
    $new_id = (int)sql_insert_id();
    if (!$new_id) {
        return array('ok' => false, 'msg' => '게시판 댓글 등록 실패 — ' . sql_error_info());
    }

    /* 부모의 댓글 수. 이걸 안 올리면 목록의 [n] 이 0 으로 남고, 스킨에 따라
       댓글이 아예 접혀 보이지 않는다. */
    sql_query("update `$wt` set wr_comment = wr_comment + 1
                where wr_id = " . (int)$parent['wr_id'], false);
    if (isset($cols['wr_last'])) {
        sql_query("update `$wt` set wr_last = '" . exbq_s($now) . "'
                    where wr_id = " . (int)$parent['wr_id'], false);
    }
    // 게시판 통계. 없어도 동작하지만 관리자 화면 숫자가 틀어진다.
    sql_query("update " . $g5['board_table'] . " set bo_count_comment = bo_count_comment + 1
                where bo_table = '" . exbq_s($bo) . "'", false);

    sql_query("update ex_qna set qa_reply_wr_id = $new_id where qa_id = $qa_id", false);

    sql_query("insert into ex_log set mb_id = '" . exbq_s($by) . "',
                 lo_act = 'qna', lo_ref = 'reply:$bo:$new_id',
                 lo_ip = '" . exbq_s($ip) . "',
                 created_at = '$now'", false);

    return array('ok' => true, 'wr_id' => $new_id, 'updated' => false);
}
