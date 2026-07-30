<?php
/**
 * exam_migrate.php — ex_* 마이그레이션 실행기.  ★ 실행 후 반드시 삭제한다.
 *
 * 배치: /www/exam_migrate.php   (웹루트. common.php 와 같은 자리)
 * 전제: /www/exam/sql/migrate-001-multipd.sql 이 먼저 올라가 있어야 한다.
 * 접근: **최고관리자로 로그인한 상태**에서만 동작한다.
 *
 * exam_install.php 와 같은 방식이고 대상 SQL 만 다르다. 두 파일을 합치지 않은 이유:
 * install 은 1회용이라 이미 서버에서 지웠고(UPLOAD-NOW.md 6단계), 그래서 이 파일은
 * ex_split_sql() 을 **자기 안에 다시 갖는다.** install 이 남아 있다고 가정하면 깨진다.
 *
 * 안전장치
 *   · ADD COLUMN/INDEX IF NOT EXISTS · ON DUPLICATE KEY UPDATE 라 여러 번 돌려도 안전
 *   · DROP TABLE · DELETE 를 하지 않는다. 기존 g5_* 는 건드리지 않는다
 *   · 인덱스는 DROP IF EXISTS → ADD IF NOT EXISTS 순서다(uq_month 재정의)
 *   · 한 문장이 실패해도 페이지가 죽지 않는다 — 실패를 우리가 세고 화면에 찍는다
 */

include_once(__DIR__ . '/common.php');

header('Content-Type: text/html; charset=utf-8');

/* ── 접근 통제 ─────────────────────────────────────────────────────────── */
if (empty($member['mb_id'])) {
    exit('<meta charset="utf-8"><p style="font:14px sans-serif">'
       . '먼저 <a href="' . G5_BBS_URL . '/login.php">최고관리자로 로그인</a>한 뒤 다시 여십시오.</p>');
}
if ($is_admin !== 'super') {
    exit('<meta charset="utf-8"><p style="font:14px sans-serif">최고관리자만 실행할 수 있습니다.</p>');
}

$SQL_FILE = __DIR__ . '/exam/sql/migrate-001-multipd.sql';
$run      = isset($_GET['run']) && $_GET['run'] === '1';

/**
 * SQL 파일을 문장 단위로 쪼갠다.
 * 따옴표 안의 `--` / `;` 를 문장 구분자로 오인하지 않도록 문자 단위로 훑는다.
 * (스토어드 프로시저·DELIMITER 는 쓰지 않으므로 이 정도로 충분하다.)
 */
function exm_split_sql($sql) {
    $out = array(); $buf = ''; $n = strlen($sql);
    $inS = false;   // '홑따옴표' 안
    $inD = false;   // "쌍따옴표" 안
    for ($i = 0; $i < $n; $i++) {
        $c  = $sql[$i];
        $c2 = ($i + 1 < $n) ? $sql[$i + 1] : '';

        if (!$inS && !$inD) {
            if ($c === '-' && $c2 === '-') {                 // -- 줄 주석
                while ($i < $n && $sql[$i] !== "\n") $i++;
                $buf .= "\n"; continue;
            }
            if ($c === '/' && $c2 === '*') {                 // /* 블록 주석 */
                $i += 2;
                while ($i < $n && !($sql[$i] === '*' && ($i + 1 < $n) && $sql[$i + 1] === '/')) $i++;
                $i++; continue;
            }
            if ($c === ';') {                                // 문장 끝
                if (trim($buf) !== '') $out[] = trim($buf);
                $buf = ''; continue;
            }
        }
        if ($c === "'" && !$inD) {
            if ($inS && $c2 === "'") { $buf .= "''"; $i++; continue; }   // '' 이스케이프
            $inS = !$inS;
        } elseif ($c === '"' && !$inS) {
            $inD = !$inD;
        } elseif ($c === '\\' && ($inS || $inD)) {           // 백슬래시 이스케이프
            $buf .= $c . $c2; $i++; continue;
        }
        $buf .= $c;
    }
    if (trim($buf) !== '') $out[] = trim($buf);
    return $out;
}

function h($s) { return htmlspecialchars((string)$s, ENT_QUOTES, 'UTF-8'); }

/** 판정 배지. */
function badge($ok, $txt) {
    return '<b class="' . ($ok ? 'ok' : 'bad') . '">' . h($txt) . '</b>';
}
?>
<!doctype html><meta charset="utf-8"><title>exam_migrate — 001 multipd</title>
<style>
 body{font:14px/1.7 ui-monospace,Consolas,monospace;max-width:1000px;margin:2rem auto;padding:0 1rem}
 h1{font-size:1.25rem} h2{font-size:1rem;margin:2rem 0 .6rem;border-bottom:1px solid #ddd;padding-bottom:4px}
 table{border-collapse:collapse;margin:.6rem 0;font-size:13px}
 td,th{border:1px solid #ccc;padding:4px 10px;text-align:left}
 th{background:#f4f5f7}
 .ok{color:#0a7f3f;font-weight:700} .bad{color:#c22638;font-weight:700} .dim{color:#888}
 .warn{background:#fff6e5;border:1px solid #d9901a;padding:.7rem 1rem;margin:1rem 0}
 .err{background:#fdeced;border:1px solid #c22638;padding:.7rem 1rem;margin:1rem 0}
 .good{background:#e9f7ef;border:1px solid #0a7f3f;padding:.7rem 1rem;margin:1rem 0}
 .btn{display:inline-block;padding:.6rem 1.4rem;background:#1f4fd8;color:#fff;text-decoration:none;border-radius:5px}
</style>

<h1>마이그레이션 001 — 문제집별 수강·포인트 <span class="dim">— 실행 후 반드시 삭제</span></h1>

<div class="warn">
  이 파일은 DB 구조를 바꾼다. <b>확인이 끝나면 즉시 <code>/www/exam_migrate.php</code> 를 삭제</b>한다.
</div>

<?php
if ($run) {
    /* ── SQL 실행 ───────────────────────────────────────────────────────── */
    echo '<h2>migrate-001-multipd.sql</h2>';

    if (!is_readable($SQL_FILE)) {
        echo '<div class="err">파일을 읽을 수 없다: <code>' . h($SQL_FILE) . '</code><br>'
           . 'FileZilla 로 <code>web/exam/sql/migrate-001-multipd.sql</code> 를 '
           . '<code>/www/exam/sql/</code> 에 먼저 올렸는지 확인한다.</div>';
    } else {
        $stmts = exm_split_sql(file_get_contents($SQL_FILE));
        $ok = $fail = 0;
        echo '<table><tr><th>#</th><th>문장</th><th>결과</th></tr>';
        foreach ($stmts as $i => $s) {
            // 두 번째 인자 false = G5_DISPLAY_SQL_ERROR 를 끄고 실패를 우리가 센다.
            // 한 문장이 죽었다고 페이지가 통째로 날아가면 원인을 못 본다.
            $r = sql_query($s, false);
            $head = preg_replace('/\s+/', ' ', mb_substr($s, 0, 78));
            if ($r) { $ok++;  $cls = 'ok';  $msg = 'OK'; }
            else    { $fail++; $cls = 'bad'; $msg = sql_error_info(); }
            echo '<tr><td>' . ($i + 1) . '</td><td>' . h($head) . '…</td>'
               . '<td class="' . $cls . '">' . h($msg) . '</td></tr>';
        }
        echo '</table>';
        echo '<p>성공 <b class="ok">' . $ok . '</b> · 실패 <b class="' . ($fail ? 'bad' : 'dim') . '">' . $fail . '</b></p>';

        if ($fail) {
            echo '<div class="err"><b>실패한 문장이 있다.</b> 위 메시지를 확인한다.<br>'
               . '· <code>IF NOT EXISTS</code> 문법 오류라면 MariaDB 가 10.0 미만이다 — '
               . '해당 절을 지우고 이미 있는 컬럼은 손으로 건너뛴다.<br>'
               . '· <code>Duplicate key name</code> 이면 DROP INDEX 가 먼저 실행되지 않았다.</div>';
        }
    }

    /* ── 검증 ───────────────────────────────────────────────────────────── */

    echo '<h2>검증 (1) pd_id 컬럼이 5개 테이블에 있는가</h2>';
    $want = array('ex_order', 'ex_plan', 'ex_credit_lot', 'ex_credit_ledger', 'ex_qna');
    $res = sql_query("select TABLE_NAME, COLUMN_TYPE, COLUMN_DEFAULT
                        from information_schema.COLUMNS
                       where TABLE_SCHEMA = database() and COLUMN_NAME = 'pd_id'
                         and TABLE_NAME in ('" . implode("','", $want) . "')
                       order by TABLE_NAME", false);
    $found = array(); $n = 0;
    echo '<table><tr><th>테이블</th><th>타입</th><th>기본값</th></tr>';
    while ($r = sql_fetch_array($res)) {
        $n++; $found[$r['TABLE_NAME']] = true;
        echo '<tr><td>' . h($r['TABLE_NAME']) . '</td><td>' . h($r['COLUMN_TYPE']) . '</td>'
           . '<td>' . h($r['COLUMN_DEFAULT'] === null ? 'NULL' : "'" . $r['COLUMN_DEFAULT'] . "'") . '</td></tr>';
    }
    echo '</table>';
    echo '<p>' . badge($n === 5, $n . ' / 5') . '</p>';
    foreach ($want as $t) {
        if (empty($found[$t])) echo '<div class="err">누락: <code>' . h($t) . '.pd_id</code></div>';
    }

    echo '<h2>검증 (2) pd_id 가 빈 행 — 전부 0 이어야 한다</h2>';
    $r = sql_fetch("select (select count(*) from ex_order         where pd_id='') as ord,
                           (select count(*) from ex_plan          where pd_id='') as pln,
                           (select count(*) from ex_credit_lot    where pd_id='') as lot,
                           (select count(*) from ex_credit_ledger where pd_id='') as lgr", false);
    if ($r === false || $r === null) {
        echo '<div class="err">조회 실패 — ' . h(sql_error_info()) . '</div>';
    } else {
        $sum = (int)$r['ord'] + (int)$r['pln'] + (int)$r['lot'] + (int)$r['lgr'];
        echo '<table><tr><th>ex_order</th><th>ex_plan</th><th>ex_credit_lot</th><th>ex_credit_ledger</th></tr><tr>'
           . '<td>' . (int)$r['ord'] . '</td><td>' . (int)$r['pln'] . '</td>'
           . '<td>' . (int)$r['lot'] . '</td><td>' . (int)$r['lgr'] . '</td></tr></table>';
        echo '<p>합계 ' . badge($sum === 0, (string)$sum) . ' <span class="dim">(0 이어야 backfill 완료)</span></p>';
    }

    echo '<h2>검증 (3) ★★ 이중 지급 차단 제약이 문제집을 포함하는가</h2>';
    $res = sql_query("show index from ex_credit_lot where Key_name = 'uq_month'", false);
    $cols = array(); $nonuniq = null;
    while ($r = sql_fetch_array($res)) {
        $cols[(int)$r['Seq_in_index']] = $r['Column_name'];
        $nonuniq = $r['Non_unique'];
    }
    ksort($cols);
    $got = implode(', ', $cols);
    $want_key = 'mb_id, pd_id, lot_src, lot_period';
    echo '<table><tr><th>현재 uq_month</th><td><code>(' . h($got) . ')</code></td></tr>'
       . '<tr><th>기대값</th><td><code>(' . h($want_key) . ')</code></td></tr>'
       . '<tr><th>Non_unique</th><td>' . h($nonuniq === null ? '—' : $nonuniq)
       . ' <span class="dim">(0 이어야 UNIQUE)</span></td></tr></table>';
    $key_ok = ($got === $want_key && (string)$nonuniq === '0');
    echo '<p>' . badge($key_ok, $key_ok ? '정상' : '불일치') . '</p>';
    if (!$key_ok) {
        echo '<div class="err"><b>여기가 틀리면 두 문제집을 수강하는 회원의 같은 달 두 번째 월 지급이'
           . ' DB 차원에서 거부된다.</b><br>'
           . '컬럼이 3개면 옛 키가 그대로다 — DROP INDEX 가 실행되지 않았는지 위 표를 확인한다.</div>';
    }

    echo '<h2>검증 (4) 문제집별 수강 과정</h2>';
    $res = sql_query("select d.pd_id, d.pd_name, d.pd_open,
                             (select count(*) from ex_problem x where x.pd_id = d.pd_id and x.pr_open = 1) as probs,
                             (select count(*) from ex_plan p where p.pd_id = d.pd_id and p.pl_open = 1) as plans
                        from ex_product d order by d.pd_sort, d.pd_id", false);
    $rows = 0; $plan_bad = 0;
    echo '<table><tr><th>pd_id</th><th>이름</th><th>노출</th><th>문제</th><th>과정</th></tr>';
    while ($r = sql_fetch_array($res)) {
        $rows++;
        $pl = (int)$r['plans'];
        if ($pl !== 3) $plan_bad++;
        echo '<tr><td><code>' . h($r['pd_id']) . '</code></td><td>' . h($r['pd_name']) . '</td>'
           . '<td>' . ((int)$r['pd_open'] ? 'Y' : 'N') . '</td>'
           . '<td>' . (int)$r['probs'] . '</td>'
           . '<td class="' . ($pl === 3 ? 'ok' : 'bad') . '">' . $pl . '</td></tr>';
    }
    echo '</table>';
    echo '<p>품목 ' . badge($rows >= 2, (string)$rows) . '개 · 과정 3개가 아닌 품목 '
       . badge($plan_bad === 0, (string)$plan_bad) . '</p>';
    echo '<p class="dim">문제 0건인 품목은 api/products.php 가 자동으로 "준비 중"으로 내려 '
       . '이용자가 빈 화면을 볼 수 없다.</p>';

    echo '<h2>검증 (5) 고아 주문 — 주문 품목과 과정 품목이 어긋난 것</h2>';
    $r = sql_fetch("select count(*) as c from ex_order o
                      join ex_plan p on p.pl_id = o.pl_id
                     where p.pd_id <> o.pd_id", false);
    if ($r === false || $r === null) {
        echo '<div class="err">조회 실패 — ' . h(sql_error_info()) . '</div>';
    } else {
        echo '<p>' . badge((int)$r['c'] === 0, (int)$r['c'] . '건') . ' <span class="dim">(0 이어야 정상)</span></p>';
    }

    echo '<h2>검증 (6) ex_qna 신규 컬럼 (과목게시판 배선)</h2>';
    $res = sql_query("select COLUMN_NAME, COLUMN_TYPE from information_schema.COLUMNS
                       where TABLE_SCHEMA = database() and TABLE_NAME = 'ex_qna'
                         and COLUMN_NAME in ('sj_no','bo_table','wr_id')
                       order by ORDINAL_POSITION", false);
    $n = 0;
    echo '<table><tr><th>컬럼</th><th>타입</th></tr>';
    while ($r = sql_fetch_array($res)) {
        $n++;
        echo '<tr><td>' . h($r['COLUMN_NAME']) . '</td><td>' . h($r['COLUMN_TYPE']) . '</td></tr>';
    }
    echo '</table>';
    echo '<p>' . badge($n === 3, $n . ' / 3') . '</p>';

    echo '<h2>검증 (7) 콜레이션 — g5_member 조인이 여전히 되는가</h2>';
    // 컬럼을 추가하면서 테이블 기본 콜레이션이 mb_id 계열에 섞이지 않았는지 확인한다.
    $r = sql_fetch("select count(*) as c from ex_credit_lot l
                      join g5_member m on m.mb_id = l.mb_id", false);
    if ($r === false || $r === null) {
        echo '<div class="err"><b>조인 실패</b> — ' . h(sql_error_info())
           . '<br>Illegal mix of collations 라면 mb_id 가 utf8mb3 이 아니게 됐다.</div>';
    } else {
        echo '<p class="ok">조인 성공. 결과 ' . (int)$r['c'] . '행 '
           . '<span class="dim">(0이어도 정상 — 아직 지급 기록이 없다)</span></p>';
    }

    echo '<div class="warn">여기까지 이상이 없으면 <b>이 파일(<code>/www/exam_migrate.php</code>)을 지운다.</b><br>'
       . '<code>/www/exam/sql/</code> 는 <code>.htaccess</code> 가 막고 있으므로 남겨도 된다.</div>';

} else {
    /* ── 실행 전 상태 확인 ──────────────────────────────────────────────── */
    echo '<h2>실행 전 확인</h2><table>';
    echo '<tr><th>DB</th><td>' . h(sql_fetch("select database() as d")['d']) . '</td></tr>';
    echo '<tr><th>서버 버전</th><td>' . h(sql_fetch("select version() as v")['v'])
       . ' <span class="dim">← IF NOT EXISTS 절은 MariaDB 10.0+ 에서 유효하다</span></td></tr>';
    echo '<tr><th>sql_mode</th><td>' . h(sql_fetch("select @@sql_mode as m")['m']) . '</td></tr>';

    $r = sql_fetch("select count(*) as c from information_schema.COLUMNS
                     where TABLE_SCHEMA = database() and COLUMN_NAME = 'pd_id'
                       and TABLE_NAME in ('ex_order','ex_plan','ex_credit_lot','ex_credit_ledger')");
    echo '<tr><th>이미 적용됨?</th><td>pd_id 컬럼 ' . (int)$r['c']
       . ' / 4 <span class="dim">(0이면 최초 실행, 4면 이미 적용됨 — 재실행해도 안전하다)</span></td></tr>';

    $res = sql_query("show index from ex_credit_lot where Key_name = 'uq_month'", false);
    $k = 0; while ($res && sql_fetch_array($res)) $k++;
    echo '<tr><th>현재 uq_month</th><td>' . $k . '컬럼 '
       . '<span class="dim">(3이면 옛 키 → 이 마이그레이션이 4로 바꾼다)</span></td></tr>';

    $r = sql_fetch("select count(*) as c from ex_order");
    echo '<tr><th>기존 주문</th><td>' . (int)$r['c'] . '건 <span class="dim">(pd_id 를 sqld 로 채운다)</span></td></tr>';
    $r = sql_fetch("select count(*) as c from ex_credit_lot");
    echo '<tr><th>기존 포인트 묶음</th><td>' . (int)$r['c'] . '건</td></tr>';

    echo '<tr><th>SQL 파일</th><td>'
       . (is_readable($SQL_FILE) ? '<span class="ok">OK</span>' : '<span class="bad">없음</span>')
       . '<br><span class="dim">' . h($SQL_FILE) . '</span></td></tr>';
    echo '</table>';

    echo '<h2>무엇을 바꾸는가</h2><table>'
       . '<tr><th>ex_order</th><td>+ pd_id · idx_mbpd <span class="dim">— 어느 문제집 신청인지 기록</span></td></tr>'
       . '<tr><th>ex_plan</th><td>+ pd_id · idx_pd <span class="dim">— 문제집별 가격·질문 수</span></td></tr>'
       . '<tr><th>ex_credit_lot</th><td>+ pd_id · <b>uq_month 재정의</b> · idx_bal '
       . '<span class="dim">— 포인트를 문제집별로</span></td></tr>'
       . '<tr><th>ex_credit_ledger</th><td>+ pd_id · idx_mbpd</td></tr>'
       . '<tr><th>ex_qna</th><td>+ sj_no · bo_table · wr_id, pd_id 기본값 제거 '
       . '<span class="dim">— 과목게시판 배선</span></td></tr>'
       . '<tr><th>마스터</th><td>bdae-w 품목 1행 + 과정 3행</td></tr>'
       . '</table>';

    echo '<p><a class="btn" href="?run=1">마이그레이션 실행</a></p>';
    echo '<p class="dim">컬럼 추가와 backfill 뿐이라 <b>적용 후에도 기존 코드가 그대로 돈다.</b> '
       . 'DROP TABLE·DELETE 는 하지 않는다.</p>';
}
