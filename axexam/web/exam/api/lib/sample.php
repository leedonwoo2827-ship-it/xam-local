<?php
/**
 * 샘플(데모) 응시 한 건 — 로그인 없이 성적표·응시이력·오답노트를 보여주기 위한 것.
 *
 * ── 왜 필요한가 ────────────────────────────────────────────────────────────
 * 성적표·오답노트는 **채점 기록이 있어야** 성립한다(`grade.php` 가 로그인 회원에게만
 * 기록한다). 그래서 신규 방문자와 강사·기획자에게 "이 제품이 무엇을 주는지" 를
 * 보여줄 방법이 원래 없었다. 가입하고 50문제를 풀어야 처음 보인다.
 *
 * ── 왜 회원 데이터를 쓰지 않는가 ──────────────────────────────────────────
 * 실제 회원의 응시 기록을 샘플로 노출하면 그게 곧 개인정보다.
 * `api/report.php` 는 `at_id` 만으로 남의 성적표를 열 수 없게 `mb_id` 를 WHERE 에
 * 넣어두었는데, 샘플이 그 방어를 우회하는 뒷문이 되면 안 된다.
 *
 * → **이 파일은 `ex_problem`·`ex_round` 만 읽는다.** 회원 테이블
 *   (`ex_attempt`·`ex_attempt_item`·`ex_wrong`·`ex_entitlement`)을 한 줄도 읽지 않는다.
 *   답안은 문제 식별자에서 **결정적으로 계산**한다 — DB 에 쓰지도 않는다.
 *
 * ── 왜 결정적인가 ─────────────────────────────────────────────────────────
 * `rand()` 를 쓰면 새로고침마다 점수가 바뀌어 데모가 우스워지고, 캡처·문서와도 어긋난다.
 * `crc32(pr_key)` 로 만들면 같은 문제집은 언제나 같은 성적표가 나온다.
 */
if (!defined('_GNUBOARD_')) exit;

/** GET sample=1 로 요청됐는가 */
function ex_sample_on()
{
    return !empty($_GET['sample']);
}

/**
 * 합성 답안지. 회원 데이터를 읽지 않는다.
 *
 * @return array|null rows(ex_problem 행 + chosen·is_ok) · 집계값 · rd_label
 */
function ex_sample_sheet($pd, $rd_no = 1)
{
    $pdq = sql_real_escape_string($pd);
    $rd_no = (int)$rd_no;

    /* 회차를 고정하지 않는다 — 문제집마다 회차 번호가 다르다(빅분기는 1회뿐).
       요청한 회차에 문제가 없으면 문제가 있는 첫 회차를 쓴다. */
    $r = sql_fetch("select rd_no from ex_problem
                     where pd_id = '$pdq' and pr_open = 1 and rd_no = $rd_no limit 1");
    if (!$r) {
        $r = sql_fetch("select rd_no from ex_problem
                         where pd_id = '$pdq' and pr_open = 1
                         order by rd_no limit 1");
        if (!$r) return null;
        $rd_no = (int)$r['rd_no'];
    }

    $res = sql_query("select pr_id, pr_key, pr_no, rd_no, sj_no, sj_name, difficulty,
                             question, choices_json, answer_index, answer_label,
                             explanation, tags_json
                        from ex_problem
                       where pd_id = '$pdq' and rd_no = $rd_no and pr_open = 1
                       order by pr_no", false);

    $rows = array();
    $correct = 0;
    $skipped = 0;
    while ($res && $row = sql_fetch_array($res)) {
        $ans = ($row['answer_index'] === null) ? -1 : (int)$row['answer_index'];
        $n   = max(1, count(ex_unjson($row['choices_json'], array())));
        $h   = crc32((string)$row['pr_key']);

        /* 미응답 3문항쯤 — '미응답이 오답으로 계산됐다' 안내가 화면에 있는데
           샘플에서 그 경로가 안 보이면 그 안내를 설명할 수 없다. */
        if ($h % 16 === 0) {
            $chosen = -1;
            $ok = 0;
            $skipped++;
        } elseif ($h % 100 < 34) {          // 34% 정답 — 과락이 보이는 점수대
            $chosen = $ans;
            $ok = 1;
            $correct++;
        } else {
            // 정답이 아닌 보기 하나를 결정적으로 고른다
            $chosen = ($ans >= 0) ? ($ans + 1 + ($h % max(1, $n - 1))) % $n : 0;
            $ok = 0;
        }

        $row['chosen'] = $chosen;
        $row['is_ok']  = $ok;
        $rows[] = $row;
    }
    if (!$rows) return null;

    $total = count($rows);
    $rd = sql_fetch("select rd_label from ex_round where pd_id = '$pdq' and rd_no = $rd_no");

    return array(
        'rd_no'    => $rd_no,
        'rd_label' => $rd ? $rd['rd_label'] : ($rd_no . '회'),
        'rows'     => $rows,
        'total'    => $total,
        'correct'  => $correct,
        'pct'      => (int)round($correct * 100 / $total),
        'skipped'  => $skipped,
        /* 날짜는 '오늘 09:28' 로 만든다. 상수로 박으면 한 달 뒤 데모에 옛 날짜가 뜨고,
           now() 로 두면 초 단위로 흔들려 캡처가 매번 달라진다. */
        'at'       => date('Y-m-d') . ' 09:28:00',
        'at_id'    => 0,
    );
}
