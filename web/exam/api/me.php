<?php
/**
 * GET /exam/api/me.php
 *
 * 내 상태 + CSRF 토큰. 화면 부팅 때 가장 먼저 부른다.
 *
 * ⚠ 지금은 **최소 버전**이다. S6(크레딧)에서 아래가 추가된다:
 *     · ex_settle($mb)  — 월 지급(drip) 정산을 여기서 먼저 돌린다
 *     · bal / count / lots / unit — 질문권 잔액
 *   `count = floor(bal / unit)` 이고 **화면에는 count 만 쓴다.**
 *   차감 단가는 노출하지 않는다(COST.md §8).
 */
require_once __DIR__ . '/_boot.php';

$mb = ex_mb();

if ($mb === '') {
    // 비로그인도 csrf 는 준다 — 익명 채점 경로에서 같은 코드를 쓰기 때문이다.
    ex_out(array(
        'ok'    => 1,
        'login' => 0,
        'csrf'  => ex_csrf(),
        'bal'   => 0,
        'count' => 0,
    ));
}

global $member;
$ext = ex_ext($mb);   // 없으면 생성

ex_out(array(
    'ok'      => 1,
    'login'   => 1,
    'mb_id'   => $mb,
    'nick'    => isset($member['mb_nick']) ? $member['mb_nick'] : $mb,
    'admin'   => ex_is_admin() ? 1 : 0,
    'csrf'    => ex_csrf(),

    // ↓ S6 에서 실제 값으로 바뀐다. 지금은 자리만 잡아둔다 —
    //   화면이 이 필드를 참조하기 시작한 뒤에 스키마를 바꾸면 더 비싸다.
    'bal'     => 0,
    'unit'    => 10,
    'count'   => 0,
    'agreed'  => !empty($ext['agree_at']) ? 1 : 0,
    'blocked' => !empty($ext['blocked'])  ? 1 : 0,
));
