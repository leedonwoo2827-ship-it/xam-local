<?php
/**
 * 품목 관리 — `ex_product` + `ex_plan` 등록 · 수정 · 숨김 · 삭제.
 * **카페24에 phpMyAdmin 이 없어서 있다.**
 *
 * ── 왜 필요한가 ────────────────────────────────────────────────────────────
 * 임포트(`adm/exam_import.php`)는 `ex_product` 에 그 품목 행이 없으면 "master.sql 을
 * 먼저 실행하십시오" 로 중단한다(`adm/exam_lib/problem.php:100`). 그런데 카페24 호스팅에는
 * phpMyAdmin 이 없어서 그 한 줄을 넣을 곳이 없다. FTP 는 있으니, 그누보드의 DB 접속과
 * 관리자 인증을 그대로 빌려 쓴다.
 *
 * 그리고 실제로 겪은 일: 같은 문제집이 `bdae-w` 와 `bigdata` 두 이름으로 생겨
 * **랜딩에 같은 이름 카드가 두 개** 뜰 상황이 됐다. 등록만 되고 정리할 방법이 없으면
 * 그런 찌꺼기가 계속 쌓인다. 그래서 수정·숨김·삭제를 함께 둔다.
 *
 * ── ★ 삭제의 안전 규칙 ─────────────────────────────────────────────────────
 * `pd_id` 를 참조하는 테이블이 다섯이다: ex_problem · ex_round · ex_entitlement ·
 * ex_order · ex_qna. 그리고 `ex_problem.pr_id` 는 **회원의 응시기록·오답노트**
 * (`ex_attempt_item.pr_id` · `ex_wrong.pr_id`)가 참조한다(schema.sql:81 의 경고).
 *
 * → 그래서 **회원 응시·오답 기록이 0건일 때만 삭제한다.** 처음에는 '문항 0개' 로 막았는데,
 *   그러면 아무도 풀지 않은 찌꺼기 품목(예전 이름으로 잘못 임포트된 것)을 정리할 수 없다.
 *   막아야 하는 것은 문항의 존재가 아니라 **그 문항을 참조하는 회원 기록**이다.
 *   기록이 있으면 [숨기기] 를 쓴다 — 이용자 화면에서 사라지고 데이터는 남는다.
 *
 * ── 이름과 pd_id ───────────────────────────────────────────────────────────
 * `pd_id` 는 짧고 안 변해야 한다 — 06/pd/<pd>/ · youtube_map.<pd>.json ·
 * ?pd=<pd> URL · bo_table=<pd>_sj · ex_problem.pd_id 다섯 곳에 박힌다. 바꾸면 새 품목이
 * 되어 전부 다시 만들어야 하고 옛 데이터가 고아로 남는다 → [고치기] 에서 readonly 다.
 * 마케팅 문구는 `pd_name` 에 담는다(예: '2026~2027 시험대비 빅데이터분석기사 필기').
 * 빌더의 `--pd-name` 은 file:// 미리보기용이고 **서버에서는 이 값이 이긴다**
 * (build_check.py:792). 재임포트도 이름을 건드리지 않는다.
 *
 * ── 안전 ───────────────────────────────────────────────────────────────────
 * - `adm/` 에 두고 `_common.php` 를 include 한다 → 그누보드 관리자 인증이 그대로 걸린다.
 *   최고관리자가 아니면 아무것도 하지 않는다(새 인증을 만들지 않는다).
 * - `pd_id` 는 `[a-z0-9-]{1,20}` 만 받는다 — 임포트(`problem.php:86`)와 같은 규칙이라
 *   여기서 통과한 값이 거기서 막히지 않는다.
 *
 * ── ★ 수강 과정(`ex_plan`)도 여기서 한다 ───────────────────────────────────
 * `ex_plan` 은 **품목별**이다(`migrate-001-multipd.sql` §2 가 `pd_id` 를 넣었다).
 * `exam/buy.php` 가 `where pd_id = '<품목>' and pl_open = 1` 로 읽으므로, 과정이 없는
 * 품목은 신청서에 **"등록된 과정이 없습니다"** 만 나오고 [신청하기] 가 없다.
 *
 * 실제로 그렇게 걸렸다: 마이그레이션이 과정 3종을 `bdae-w` 에 심었는데, 품목을 새로
 * `bigdata` 로 등록했다. SQLD 는 신청서가 뜨고 빅분기는 안 떴다 — DB 를 열어 볼 방법이
 * 없으니 원인을 찾을 데가 없었다. 그래서 두 가지를 여기에 둔다:
 *   · 품목 표에 **과정 수 열** — 0 이면 그 자리에서 보인다
 *   · [기본 3종 만들기] — 1·3·12개월 × 매월 질문 100개를 한 번에 (SQLD 와 같은 구성)
 *
 * 삭제는 `ex_order.pl_id` 가 그 과정을 참조하면 막는다 — 주문 이력의 과정명이
 * 사라지면 안 된다. 대신 [숨기기](`pl_open = 0`) 를 쓴다: 신청서에서 빠지고
 * 기존 주문·구독은 그대로 유지된다.
 *
 * ── 쓰는 법 ────────────────────────────────────────────────────────────────
 * FTP 로 `/www/adm/seed_pd.php` 에 올리고, 최고관리자로 로그인한 브라우저에서 연다.
 * 쓰고 나면 지운다 — 관리자만 쓸 수 있지만 둘 이유가 없다.
 */
require_once './_common.php';

/* 그누보드의 최고관리자 게이트 — `g4_import.php` 가 쓰는 것과 같은 패턴이다.
   새 인증 수단을 만들지 않는다(만들면 그게 곧 구멍이 된다). */
if ($is_admin != 'super') {
    alert('최고관리자로 로그인 후 실행해 주십시오.', G5_URL);
}

$PD_RE = '/^[a-z0-9\-]{1,20}$/';
$msg = '';
$err = '';

/* ── 처리 ──────────────────────────────────────────────────────────────── */
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $act   = isset($_POST['act']) ? $_POST['act'] : '';
    $pd_id = isset($_POST['pd_id']) ? trim((string)$_POST['pd_id']) : '';

    /* ── 수강 과정(ex_plan) — `pl_` 로 시작하는 동작 ────────────────────────
     *
     * 품목 동작보다 **먼저** 갈라낸다. 숨기기·삭제는 pl_id 만 넘기고 pd_id 가 없어서,
     * 아래 $PD_RE 검사에 걸리면 "pd_id 형식이 잘못됐습니다" 가 뜬다.
     */
    if (strncmp($act, 'pl_', 3) === 0) {
        $pl_id = isset($_POST['pl_id']) ? (int)$_POST['pl_id'] : 0;

        if ($act === 'pl_seed' || $act === 'pl_save') {
            if (!preg_match($PD_RE, $pd_id)) {
                $err = "pd_id 형식이 잘못됐습니다: '" . htmlspecialchars($pd_id) . "'";
            } elseif (!sql_fetch("select pd_id from ex_product
                                   where pd_id = '" . sql_escape_string($pd_id) . "'")) {
                $err = "ex_product 에 '" . htmlspecialchars($pd_id)
                     . "' 이 없습니다. 품목을 먼저 등록하세요.";
            }
        }

        if ($err === '' && $act === 'pl_seed') {
            /* SQLD 와 **같은 3종**을 만든다. 가격·질문 수를 여기서 정하는 이유는,
               품목마다 다르게 두면 어느 것이 표준인지 알 수 없어지기 때문이다.
               다르게 하고 싶으면 만든 뒤 [고치기] 로 바꾼다.

               pl_id 를 명시하지 않는다 — 마이그레이션은 재실행 안전을 위해 1~3·11~13 을
               박았지만, 이 화면은 사람이 한 번 누르는 것이라 AUTO_INCREMENT 로 충분하다.
               같은 이름이 이미 있으면 만들지 않는다(두 번 눌러도 6개가 되지 않는다). */
            $seed = array(
                array('1개월 · 매월 질문 100개',   1100,  1, 1000, 10),
                array('3개월 · 매월 질문 100개',   3000,  3, 1000, 20),
                array('12개월 · 매월 질문 100개', 11000, 12, 1000, 30),
            );
            $pdq = sql_escape_string($pd_id);
            $made = 0; $kept = 0;
            foreach ($seed as $s) {
                $nq = sql_escape_string($s[0]);
                if (sql_fetch("select pl_id from ex_plan
                                where pd_id = '$pdq' and pl_name = '$nq'")) { $kept++; continue; }
                sql_query("insert into ex_plan
                             (pd_id, pl_name, pl_price, pl_months, pl_quota, pl_open, pl_sort)
                           values ('$pdq', '$nq', {$s[1]}, {$s[2]}, {$s[3]}, 1, {$s[4]})");
                $made++;
            }
            $msg = "$pd_id — 과정 {$made}개를 만들었습니다"
                 . ($kept ? " (같은 이름 {$kept}개는 그대로 두었습니다)." : ".")
                 . " 이제 /exam/buy.php?pd=$pd_id 에 신청서가 뜹니다.";

        } elseif ($err === '' && $act === 'pl_save') {
            $pl_name  = trim((string)$_POST['pl_name']);
            $pl_price = (int)$_POST['pl_price'];
            $pl_mon   = (int)$_POST['pl_months'];
            $pl_quota = (int)$_POST['pl_quota'];
            $pl_sort  = (int)$_POST['pl_sort'];
            if ($pl_name === '')                 $err = '과정 이름이 비어 있습니다.';
            elseif ($pl_price < 0)               $err = '가격이 음수입니다.';
            elseif ($pl_mon < 1 || $pl_mon > 60) $err = '개월 수는 1~60 입니다.';
            elseif ($pl_quota < 0)               $err = '월 지급액이 음수입니다.';
            else {
                $set = "pd_id = '" . sql_escape_string($pd_id) . "',"
                     . "pl_name = '" . sql_escape_string($pl_name) . "',"
                     . "pl_price = $pl_price, pl_months = $pl_mon,"
                     . "pl_quota = $pl_quota, pl_sort = $pl_sort";
                if ($pl_id > 0) {
                    /* ★ 이미 판 과정의 **가격·기간을 고치면** 지난 주문의 뜻이 달라진다.
                       ex_order 는 pl_id 만 들고 있어서, 표에 주문 수를 같이 보여 준다. */
                    sql_query("update ex_plan set $set where pl_id = $pl_id");
                    $msg = "과정 #$pl_id 을 저장했습니다 — $pl_name";
                } else {
                    sql_query("insert into ex_plan set $set, pl_open = 1");
                    $msg = "과정을 추가했습니다 — $pd_id · $pl_name";
                }
            }

        } elseif ($err === '' && ($act === 'pl_hide' || $act === 'pl_show')) {
            $to = ($act === 'pl_show') ? 1 : 0;
            sql_query("update ex_plan set pl_open = $to where pl_id = $pl_id");
            $msg = $to
                ? "과정 #$pl_id 을 공개했습니다."
                : "과정 #$pl_id 을 숨겼습니다. 신청서에서 빠지고 기존 주문·구독은 그대로입니다.";

        } elseif ($err === '' && $act === 'pl_delete') {
            /* 주문이 이 과정을 참조하면 지우지 않는다 — ex_order 는 pl_id 만 들고 있어서
               과정 행이 없어지면 그 주문이 "무엇을 산 것인지" 를 잃는다. */
            $o = sql_fetch("select count(*) as n from ex_order where pl_id = $pl_id");
            $n_ord = (int)$o['n'];
            if ($n_ord > 0) {
                $err = "주문 {$n_ord}건이 이 과정을 참조해 삭제할 수 없습니다. "
                     . "[숨기기] 를 쓰세요 — 신청서에서 빠지고 이력은 남습니다.";
            } else {
                sql_query("delete from ex_plan where pl_id = $pl_id");
                $msg = "과정 #$pl_id 을 삭제했습니다 (참조하는 주문이 0건이었습니다).";
            }
        }

    } elseif (!preg_match($PD_RE, $pd_id)) {
        $err = "pd_id 형식이 잘못됐습니다: '" . htmlspecialchars($pd_id)
             . "' (소문자·숫자·하이픈 1~20자)";
    } else {
        $pdq = sql_escape_string($pd_id);
        $c0 = sql_fetch("select count(*) as n from ex_problem where pd_id = '$pdq'");
        $n_prob = (int)$c0['n'];

        if ($act === 'save') {
            /* 등록 · 수정 — 같은 pd_id 면 이름·정렬만 갱신한다(UPSERT).
               pd_open 은 여기서 건드리지 않는다 — 숨김/공개는 아래 토글이 담당한다.
               새로 만들 때만 1(공개)로 들어간다. */
            $name = trim((string)$_POST['pd_name']);
            $sort = (int)$_POST['pd_sort'];
            if ($name === '') {
                $err = '품목 이름이 비어 있습니다.';
            } else {
                sql_query("insert into ex_product
                             (pd_id, pd_name, pd_open, tier, model_id, provider,
                              cost_units, cost_cap, pd_sort)
                           values
                             ('$pdq', '" . sql_escape_string($name) . "', 1, 'T1',
                              'deepseek-v4-flash', 'openai_compat', 10, 3.0000, $sort)
                           on duplicate key update
                             pd_name = values(pd_name),
                             pd_sort = values(pd_sort)");
                $msg = "저장했습니다 — $pd_id · $name · 정렬 $sort";
            }
        } elseif ($act === 'hide' || $act === 'show') {
            $to = ($act === 'show') ? 1 : 0;
            sql_query("update ex_product set pd_open = $to where pd_id = '$pdq'");
            $msg = $to
                ? "$pd_id 을 공개했습니다."
                : "$pd_id 을 숨겼습니다. 랜딩 카드와 목록에서 사라집니다"
                  . ($n_prob ? " (문항 {$n_prob}개는 그대로 남습니다)." : ".");
        } elseif ($act === 'delete') {
            /* ★ 막아야 하는 것은 "문항이 있다" 가 아니라 **"회원이 그 문항으로 풀었다"** 다.
             *
             *   처음에는 문항 0개일 때만 지우게 했는데, 그러면 아무도 풀지 않은 찌꺼기
             *   품목(예: 예전 이름으로 잘못 임포트된 것)을 정리할 수 없다. 실제로
             *   같은 문제집이 두 이름(bdae-w · bigdata)으로 생긴 상황을 만났다.
             *
             *   위험한 것은 `ex_attempt_item.pr_id` · `ex_wrong.pr_id` 다
             *   (schema.sql:81 — "pr_id 는 절대 바뀌면 안 된다"). 그 참조가 0 이면
             *   지워도 끊길 기록이 없다. 하나라도 있으면 [숨기기] 를 쓴다.
             */
            $u = sql_fetch("select
                    (select count(*) from ex_attempt_item i
                       join ex_problem p on p.pr_id = i.pr_id
                      where p.pd_id = '$pdq') as tries,
                    (select count(*) from ex_wrong w
                       join ex_problem p on p.pr_id = w.pr_id
                      where p.pd_id = '$pdq') as wrongs");
            $n_try   = (int)$u['tries'];
            $n_wrong = (int)$u['wrongs'];

            if ($n_try > 0 || $n_wrong > 0) {
                $err = "회원 기록이 있어 삭제할 수 없습니다 — 응시 {$n_try}건 · 오답노트 "
                     . "{$n_wrong}건. 지우면 그 기록이 끊깁니다. [숨기기] 를 쓰세요 "
                     . "(이용자 화면에서 사라지고 기록은 남습니다).";
            } else {
                // 참조가 없으므로 문항·회차·품목을 함께 지운다.
                sql_query("delete from ex_problem where pd_id = '$pdq'");
                sql_query("delete from ex_round   where pd_id = '$pdq'");
                sql_query("delete from ex_product where pd_id = '$pdq'");
                $msg = "$pd_id 을 삭제했습니다 — 문항 {$n_prob}개 · 회차 · 품목행. "
                     . "회원 응시기록이 0건이라 끊길 기록이 없었습니다.";
            }
        }
    }
}

/* ── 목록 — 문항·회차·구독 수를 함께 센다. 무엇을 지우는지 알고 눌러야 한다. ── */
$rows = array();
$res = sql_query("select pd_id, pd_name, pd_open, pd_sort from ex_product
                   order by pd_open desc, pd_sort, pd_id");
while ($r = sql_fetch_array($res)) {
    $pdq = sql_escape_string($r['pd_id']);
    $c = sql_fetch("select count(*) as n, count(distinct rd_no) as rd
                      from ex_problem where pd_id = '$pdq'");
    $r['n_prob']  = (int)$c['n'];
    $r['n_round'] = (int)$c['rd'];
    $e = sql_fetch("select count(*) as n from ex_entitlement where pd_id = '$pdq'");
    $r['n_ent'] = (int)$e['n'];
    /* 회원 기록 — 삭제 가능 여부를 정하는 유일한 기준이다(문항 수가 아니다). */
    $u = sql_fetch("select
            (select count(*) from ex_attempt_item i
               join ex_problem p on p.pr_id = i.pr_id where p.pd_id = '$pdq') as tries,
            (select count(*) from ex_wrong w
               join ex_problem p on p.pr_id = w.pr_id where p.pd_id = '$pdq') as wrongs");
    $r['n_try']  = (int)$u['tries'];
    $r['n_used'] = (int)$u['tries'] + (int)$u['wrongs'];
    /* ★ 열려 있는 수강 과정 수. 0 이면 `buy.php` 가 신청서 대신 "등록된 과정이 없습니다" 를
       띄운다 — 그 상태를 표에서 바로 보이게 하려고 센다(실제로 못 찾아 한참 걸렸다). */
    $p = sql_fetch("select count(*) as n from ex_plan
                     where pd_id = '$pdq' and pl_open = 1");
    $r['n_plan'] = (int)$p['n'];
    $rows[] = $r;
}

/* ── 수강 과정 목록 — 주문 수를 함께 센다(삭제 가능 여부의 기준). ────────────── */
$plans = array();
$res = sql_query("select pl_id, pd_id, pl_name, pl_price, pl_months, pl_quota, pl_open, pl_sort
                    from ex_plan order by pd_id, pl_sort, pl_id");
while ($r = sql_fetch_array($res)) {
    $o = sql_fetch("select count(*) as n from ex_order where pl_id = " . (int)$r['pl_id']);
    $r['n_ord'] = (int)$o['n'];
    $plans[] = $r;
}

/* 과정 고치기 대상 */
$pledit = null;
if (isset($_GET['pledit'])) {
    foreach ($plans as $r) {
        if ((int)$r['pl_id'] === (int)$_GET['pledit']) { $pledit = $r; break; }
    }
}

/* 수정 대상 — 목록의 [고치기] 가 넘긴다. 없으면 새 등록 폼이다. */
$edit = null;
if (isset($_GET['edit'])) {
    foreach ($rows as $r) {
        if ($r['pd_id'] === $_GET['edit']) { $edit = $r; break; }
    }
}
$f_id   = $edit ? $edit['pd_id']   : 'bigdata';
$f_name = $edit ? $edit['pd_name'] : '빅데이터분석기사 필기';
$f_sort = $edit ? (int)$edit['pd_sort'] : 20;
?><!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<title>품목 관리 (1회용)</title>
<style>
 body{font:14px/1.7 -apple-system,"Malgun Gothic",sans-serif;max-width:940px;margin:32px auto;padding:0 16px;color:#1b1f19}
 h1{font-size:19px;margin:0 0 4px} h3{font-size:15px;margin:22px 0 6px}
 .m{color:#666;font-size:13px}
 table{border-collapse:collapse;width:100%;margin:14px 0}
 th,td{border:1px solid #ddd;padding:7px 9px;text-align:left;font-size:13px;vertical-align:middle}
 th{background:#f6f6f2;white-space:nowrap}
 td.c{text-align:center}
 tr.off td{background:#faf9f5;color:#888}
 label{display:block;margin:10px 0 3px;font-weight:600;font-size:13px}
 input{width:100%;padding:6px 8px;border:1px solid #ccc;border-radius:4px;font:inherit}
 .ok{background:#e3f1ec;border:1px solid #0f7355;color:#0f7355;padding:9px 11px;border-radius:5px;margin:12px 0}
 .er{background:#f6e7ef;border:1px solid #6b1d4a;color:#6b1d4a;padding:9px 11px;border-radius:5px;margin:12px 0}
 .w{background:#f8f6e6;border:1px solid #6f6112;color:#6f6112;padding:9px 11px;border-radius:5px;margin:12px 0}
 button{padding:5px 11px;border:0;border-radius:4px;font:inherit;cursor:pointer;background:#e8e8e0}
 button.p{background:#c41c0b;color:#fff;font-weight:700;padding:9px 18px;margin-top:14px}
 button.d{background:#6b1d4a;color:#fff}
 button:disabled{opacity:.35;cursor:not-allowed}
 form.inline{display:inline}
 a{color:#cd240e}
</style></head><body>

<h1>품목 관리 <span class="m">(ex_product · 1회용)</span></h1>
<p class="m">임포트는 이 행이 없으면 중단됩니다. 카페24에 phpMyAdmin 이 없어 이 화면으로 대신합니다.</p>

<?php if ($msg): ?><div class="ok"><?php echo htmlspecialchars($msg) ?></div><?php endif; ?>
<?php if ($err): ?><div class="er"><?php echo htmlspecialchars($err) ?></div><?php endif; ?>

<h3>지금 등록된 품목</h3>
<table>
  <tr><th>pd_id</th><th>이름</th><th>문항</th><th>회차</th><th>과정</th><th>구독</th>
      <th>응시</th><th>공개</th><th>정렬</th><th>동작</th></tr>
<?php if (!$rows): ?>
  <tr><td colspan="10" class="m">없습니다. 아래에서 등록하세요.</td></tr>
<?php endif; ?>
<?php foreach ($rows as $r):
    $open = ((int)$r['pd_open'] === 1); ?>
  <tr class="<?php echo $open ? '' : 'off' ?>">
    <td><code><?php echo htmlspecialchars($r['pd_id']) ?></code></td>
    <td><?php echo htmlspecialchars($r['pd_name']) ?></td>
    <td class="c"><?php echo number_format($r['n_prob']) ?></td>
    <td class="c"><?php echo $r['n_round'] ?></td>
    <td class="c"><?php if ($r['n_plan']): echo $r['n_plan'];
                        else: ?><b style="color:#6b1d4a">0</b><?php endif; ?></td>
    <td class="c"><?php echo $r['n_ent'] ?></td>
    <td class="c"><?php echo number_format($r['n_try']) ?></td>
    <td class="c"><?php echo $open ? '공개' : '숨김' ?></td>
    <td class="c"><?php echo (int)$r['pd_sort'] ?></td>
    <td style="white-space:nowrap">
      <a href="?edit=<?php echo urlencode($r['pd_id']) ?>"><button type="button">고치기</button></a>
      <form method="post" class="inline">
        <input type="hidden" name="pd_id" value="<?php echo htmlspecialchars($r['pd_id']) ?>">
        <input type="hidden" name="act" value="<?php echo $open ? 'hide' : 'show' ?>">
        <button type="submit"><?php echo $open ? '숨기기' : '공개' ?></button>
      </form>
      <form method="post" class="inline"
            onsubmit="return confirm('<?php echo htmlspecialchars($r['pd_id']) ?> 을 삭제합니다.\n되돌릴 수 없습니다. 계속할까요?')">
        <input type="hidden" name="pd_id" value="<?php echo htmlspecialchars($r['pd_id']) ?>">
        <input type="hidden" name="act" value="delete">
        <button type="submit" class="d"
          <?php echo $r['n_used']
            ? 'disabled title="회원 응시·오답 기록이 있어 삭제할 수 없습니다 — 숨기기를 쓰세요"'
            : '' ?>>삭제</button>
      </form>
      <?php if (!$r['n_plan']): /* 과정이 0 이면 여기서 바로 만들 수 있게 둔다 */ ?>
      <form method="post" class="inline">
        <input type="hidden" name="pd_id" value="<?php echo htmlspecialchars($r['pd_id']) ?>">
        <input type="hidden" name="act" value="pl_seed">
        <button type="submit" style="background:#0f7355;color:#fff">＋과정 3종</button>
      </form>
      <?php endif; ?>
    </td>
  </tr>
<?php endforeach; ?>
</table>

<p class="m">
  <b>문항</b>이 0 이면 랜딩 카드가 '준비 중' 으로 뜹니다(<code>products.php</code> 가 그렇게
  판정합니다). <b>구독</b>은 <code>ex_entitlement</code> 행 수 — 그 품목을 수강 중인 회원 수입니다.<br>
  <b>응시</b>는 회원이 그 품목 문항을 푼 기록 수입니다 — <b>삭제 가능 여부의 유일한 기준</b>입니다.
  0 이면 문항이 있어도 지울 수 있고(찌꺼기 품목 정리), 1건이라도 있으면 잠깁니다.<br>
  ★ <b>웬만하면 [숨기기]</b>를 쓰세요. 이용자 화면에서 사라지고 데이터는 남으니 언제든
  되돌릴 수 있습니다. 삭제는 되돌릴 수 없습니다 — 확실히 버릴 것만 지웁니다.
</p>

<h3><?php echo $edit ? '품목 고치기' : '품목 등록' ?></h3>
<form method="post">
  <input type="hidden" name="act" value="save">
  <label>pd_id <span class="m">— 빌드의 <code>--pd</code> 와 같아야 합니다<?php
    echo $edit ? ' (고치기에서는 바꾸지 않습니다 — 바꾸면 새 품목이 됩니다)' : '' ?></span></label>
  <input name="pd_id" value="<?php echo htmlspecialchars($f_id) ?>" required
         <?php echo $edit ? 'readonly style="background:#f4f4f0"' : '' ?>>
  <label>품목 이름</label>
  <input name="pd_name" value="<?php echo htmlspecialchars($f_name) ?>" required>
  <label>정렬 순서 <span class="m">— 작은 값이 앞. 같으면 pd_id 순</span></label>
  <input name="pd_sort" value="<?php echo $f_sort ?>">
  <button type="submit" class="p"><?php echo $edit ? '저장' : '등록' ?></button>
  <?php if ($edit): ?>
    &nbsp; <a href="seed_pd.php">새 등록으로 돌아가기</a>
  <?php endif; ?>
</form>

<hr style="margin:30px 0;border:0;border-top:1px solid #ddd">

<h3>수강 과정 <span class="m">(ex_plan · 품목별)</span></h3>
<p class="m">
  <code>exam/buy.php</code> 는 <b>그 품목의 열린 과정만</b> 읽습니다
  (<code>where pd_id = '&lt;품목&gt;' and pl_open = 1</code>).
  과정이 0 이면 신청서 자리에 <b>“등록된 과정이 없습니다”</b> 만 나오고 [신청하기] 버튼이
  없습니다 — 위 표의 <b>과정</b> 열이 <b style="color:#6b1d4a">0</b> 인 품목이 그 상태입니다.<br>
  가장 쉬운 길은 그 품목 줄의 <b>[＋과정 3종]</b> 입니다. SQLD 와 같은 1·3·12개월
  구성이 한 번에 들어갑니다.
</p>

<table>
  <tr><th>#</th><th>품목</th><th>과정 이름</th><th>가격</th><th>기간</th>
      <th>월 지급</th><th>주문</th><th>공개</th><th>정렬</th><th>동작</th></tr>
<?php if (!$plans): ?>
  <tr><td colspan="10" class="m">없습니다. 위 표의 [＋과정 3종] 을 누르세요.</td></tr>
<?php endif; ?>
<?php foreach ($plans as $r):
    $open = ((int)$r['pl_open'] === 1); ?>
  <tr class="<?php echo $open ? '' : 'off' ?>">
    <td class="c"><?php echo (int)$r['pl_id'] ?></td>
    <td><code><?php echo htmlspecialchars($r['pd_id']) ?></code></td>
    <td><?php echo htmlspecialchars($r['pl_name']) ?></td>
    <td class="c"><?php echo number_format((int)$r['pl_price']) ?>원</td>
    <td class="c"><?php echo (int)$r['pl_months'] ?>개월</td>
    <td class="c"><?php echo number_format((int)$r['pl_quota']) ?>원</td>
    <td class="c"><?php echo (int)$r['n_ord'] ?></td>
    <td class="c"><?php echo $open ? '공개' : '숨김' ?></td>
    <td class="c"><?php echo (int)$r['pl_sort'] ?></td>
    <td style="white-space:nowrap">
      <a href="?pledit=<?php echo (int)$r['pl_id'] ?>"><button type="button">고치기</button></a>
      <form method="post" class="inline">
        <input type="hidden" name="pl_id" value="<?php echo (int)$r['pl_id'] ?>">
        <input type="hidden" name="act" value="<?php echo $open ? 'pl_hide' : 'pl_show' ?>">
        <button type="submit"><?php echo $open ? '숨기기' : '공개' ?></button>
      </form>
      <form method="post" class="inline"
            onsubmit="return confirm('과정 #<?php echo (int)$r['pl_id'] ?> 을 삭제합니다.\n계속할까요?')">
        <input type="hidden" name="pl_id" value="<?php echo (int)$r['pl_id'] ?>">
        <input type="hidden" name="act" value="pl_delete">
        <button type="submit" class="d"
          <?php echo $r['n_ord']
            ? 'disabled title="이 과정을 참조하는 주문이 있어 삭제할 수 없습니다 — 숨기기를 쓰세요"'
            : '' ?>>삭제</button>
      </form>
    </td>
  </tr>
<?php endforeach; ?>
</table>

<p class="m">
  <b>월 지급</b>은 매달 넣어주는 질문 포인트(원)입니다. <code>ex_product.cost_units</code> 가
  질문 1건의 단가라, 기본값 <code>1000원 ÷ 10원 = 월 질문 100개</code> 입니다.<br>
  <b>주문</b>은 <code>ex_order.pl_id</code> 가 이 과정을 가리키는 건수 — <b>삭제 가능 여부의
  유일한 기준</b>입니다. 1건이라도 있으면 잠깁니다(주문이 “무엇을 산 것인지” 를 잃습니다).<br>
  ★ 이미 판 과정의 <b>가격·기간을 고치면 지난 주문의 뜻이 달라집니다.</b> 값을 바꿀 때는
  고치지 말고 <b>새 과정을 만들고 옛것을 [숨기기]</b> 하세요.
</p>

<h3><?php echo $pledit ? '과정 고치기 #' . (int)$pledit['pl_id'] : '과정 직접 추가' ?></h3>
<form method="post">
  <input type="hidden" name="act" value="pl_save">
  <?php if ($pledit): ?>
    <input type="hidden" name="pl_id" value="<?php echo (int)$pledit['pl_id'] ?>">
  <?php endif; ?>
  <label>품목</label>
  <select name="pd_id" style="width:100%;padding:6px 8px;border:1px solid #ccc;border-radius:4px;font:inherit">
<?php foreach ($rows as $r): ?>
    <option value="<?php echo htmlspecialchars($r['pd_id']) ?>"<?php
      echo ($pledit && $pledit['pd_id'] === $r['pd_id']) ? ' selected' : '' ?>><?php
      echo htmlspecialchars($r['pd_id'] . ' — ' . $r['pd_name']) ?></option>
<?php endforeach; ?>
  </select>
  <label>과정 이름 <span class="m">— 신청서에 이 문구가 그대로 나옵니다</span></label>
  <input name="pl_name" required
         value="<?php echo htmlspecialchars($pledit ? $pledit['pl_name'] : '1개월 · 매월 질문 100개') ?>">
  <label>가격 <span class="m">— 원, VAT 포함</span></label>
  <input name="pl_price" value="<?php echo $pledit ? (int)$pledit['pl_price'] : 1100 ?>">
  <label>기간 <span class="m">— 개월</span></label>
  <input name="pl_months" value="<?php echo $pledit ? (int)$pledit['pl_months'] : 1 ?>">
  <label>월 지급액 <span class="m">— 원. 1000 = 질문 100개 (단가 10원)</span></label>
  <input name="pl_quota" value="<?php echo $pledit ? (int)$pledit['pl_quota'] : 1000 ?>">
  <label>정렬 순서 <span class="m">— 작은 값이 앞</span></label>
  <input name="pl_sort" value="<?php echo $pledit ? (int)$pledit['pl_sort'] : 10 ?>">
  <button type="submit" class="p"><?php echo $pledit ? '저장' : '추가' ?></button>
  <?php if ($pledit): ?>
    &nbsp; <a href="seed_pd.php">새로 추가하기로 돌아가기</a>
  <?php endif; ?>
</form>

<div class="w" style="margin-top:22px">
  끝나면 <b>이 파일을 FTP 로 지우세요</b> (<code>/adm/seed_pd.php</code>).
  관리자만 쓸 수 있지만 둘 이유가 없습니다.
</div>
</body></html>
