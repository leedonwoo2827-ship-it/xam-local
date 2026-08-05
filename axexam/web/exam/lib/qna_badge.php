<?php
/**
 * 게시판 스킨용 — 글마다 `답변완료` 배지.
 *
 * ── 왜 스킨이 이걸 직접 못 하는가 ──────────────────────────────────────────
 * 답변 여부의 정본은 게시판이 아니라 **`ex_qna.qa_status = 'approved'`** 다.
 * 게시판의 댓글 수로 판정하면 회원끼리 주고받은 댓글까지 세어 "답변완료"가 켜진다.
 * 관리자가 확정한 답변만 완료다 — `exam/api/board.php` 도 같은 기준을 쓴다.
 *
 * ── 왜 별도 파일인가 ───────────────────────────────────────────────────────
 * 게시판 스킨은 그누보드 코어(`skin/board/<이름>/`) 아래 있어서 우리 저장소에 없다.
 * 스킨에 SQL 을 적으면 (a) 스킨을 갈아탈 때마다 다시 쓰고 (b) 우리가 판정 규칙을
 * 고쳐도 스킨은 옛 규칙을 쓴다. 그래서 판정은 여기 한 곳에 두고 스킨은 **두 줄만** 부른다.
 *
 * ── 쓰는 법 (list.skin.php) ────────────────────────────────────────────────
 *   ① 목록 루프 **앞**에서 한 번:
 *        include_once G5_PATH.'/exam/lib/qna_badge.php';
 *        $ex_ans = ex_qna_answered($bo_table, $list);
 *
 *   ② 제목 옆(루프 안):
 *        echo ex_qna_badge($ex_ans, $list[$i]['wr_id']);
 *
 * ★ 한 페이지에 쿼리 **1회**다. 행마다 부르면 30건에 30쿼리가 된다(N+1).
 *   그래서 목록 배열을 통째로 받아 한 번에 조회한다.
 *
 * ★ 스타일을 인라인으로 넣는다. 스킨마다 CSS 클래스 체계가 달라서, 클래스만 뿌리면
 *   어떤 스킨에서는 아무 모양 없이 글자만 붙는다. 배지는 눈에 보여야 뜻이 있다.
 */
if (!defined('_GNUBOARD_')) exit;

/**
 * 목록에서 답변이 확정된 글의 wr_id 집합.
 *
 * @param string $bo_table 게시판 테이블명 (`bigdata_sj`)
 * @param array  $list     그누보드 목록 배열(`$list`) 또는 wr_id 배열
 * @return array  wr_id => 'done'|'wait'  (없는 wr_id 는 키가 없다)
 */
function ex_qna_answered($bo_table, $list)
{
    $ids = array();
    if (is_array($list)) {
        foreach ($list as $row) {
            if (is_array($row) && isset($row['wr_id'])) $ids[] = (int)$row['wr_id'];
            elseif (is_numeric($row))                   $ids[] = (int)$row;
        }
    }
    $ids = array_values(array_unique(array_filter($ids)));
    if (!$ids) return array();

    /* 게시판 이름은 [a-z0-9_] 로만 좁힌다 — 스킨이 넘겨주는 값이라 신뢰하지 않는다. */
    $bo = preg_replace('/[^a-z0-9_]/', '', strtolower((string)$bo_table));
    if ($bo === '') return array();

    /* ★ `답변완료` 는 **게시판에 답이 실제로 있다**는 뜻이어야 한다.
     *
     *   처음에는 `qa_status = 'approved'` 만 봤다. 그런데 관리자가 게시판에서 답변
     *   댓글을 지우면 우리 DB 는 여전히 approved 라서 **배지가 초록으로 남았다.**
     *   회원 입장에서는 '답변완료' 를 보고 글을 열었는데 답이 없다 — 배지가 거짓말을
     *   하는 상태다(실제로 그렇게 걸렸다).
     *
     *   그래서 우리가 쓴 답변 댓글(`qa_reply_wr_id`)이 **살아 있는지 같이 본다.**
     *   서브쿼리 하나라 여전히 페이지당 쿼리 1회다.
     *
     *   approved 인데 댓글이 없으면 `wait` 로 둔다 — 배지는 "게시판에 무엇이 있는가"
     *   를 말하는 것이고, 회원에게는 아직 답이 없는 것이 사실이다.
     *   운영자는 검수 화면에서 진짜 상태(완료)와 경고 문구를 본다.
     */
    global $g5;
    $wt = $g5['write_prefix'] . $bo;      // $bo 는 위에서 [a-z0-9_] 로 좁혔다

    $out = array();
    $res = sql_query("select q.wr_id, q.qa_status,
                             (select 1 from `$wt` c
                               where c.wr_id = q.qa_reply_wr_id
                                 and c.wr_is_comment = 1) as has_reply
                        from ex_qna q
                       where q.bo_table = '" . sql_real_escape_string($bo) . "'
                         and q.wr_id in (" . implode(',', $ids) . ")", false);
    /* ★ 실패해도 죽지 않는다. 배지는 부가 정보라, 못 읽으면 배지만 없으면 된다 —
       게시판 목록 자체가 흰 화면이 되는 것이 훨씬 나쁘다.
       (qa_reply_wr_id 컬럼이 아직 없는 서버에서도 여기가 조용히 빈 배열이 된다.) */
    while ($res && $r = sql_fetch_array($res)) {
        $done = ($r['qa_status'] === 'approved') && !empty($r['has_reply']);
        $out[(int)$r['wr_id']] = $done ? 'done' : 'wait';
    }
    return $out;
}

/**
 * 배지 HTML 한 조각. 해당 글이 큐에 없으면 빈 문자열(아무것도 안 붙는다).
 *
 * `wait` 도 보여주는 이유: 질문자가 "접수는 됐나"를 알아야 재질문이 줄어든다.
 * 다만 `done` 보다 약하게 — 완료가 눈에 먼저 들어와야 한다.
 */
function ex_qna_badge($map, $wr_id, $show_wait = true)
{
    $st = isset($map[(int)$wr_id]) ? $map[(int)$wr_id] : '';
    if ($st === 'done') {
        return ' <span style="display:inline-block;padding:1px 7px;border-radius:999px;'
             . 'background:#e9f7ef;color:#075c2d;border:1px solid #9fd6b6;'
             . 'font-size:11.5px;font-weight:700;vertical-align:middle;white-space:nowrap">'
             . '답변완료</span>';
    }
    if ($st === 'wait' && $show_wait) {
        return ' <span style="display:inline-block;padding:1px 7px;border-radius:999px;'
             . 'background:#fff6e5;color:#8a5a00;border:1px solid #e6cf9a;'
             . 'font-size:11.5px;font-weight:600;vertical-align:middle;white-space:nowrap">'
             . '답변 준비 중</span>';
    }
    return '';
}
