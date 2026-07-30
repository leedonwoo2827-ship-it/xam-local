<?php
/**
 * GET /exam/api/videos.php?pd=sqld
 *
 * **레벨 제한 해설 영상**만 내려준다. 공개 영상은 pd/<pd>/videos.js 에 이미 들어 있다.
 *
 * ── 왜 API 가 필요한가 ─────────────────────────────────────────────────────
 * videos.js 는 정적 파일이라 주소만 알면 누구나 내려받는다.
 * 화면에서 레벨을 보고 버튼을 숨겨도 **링크는 파일 안에 그대로 남는다** — 가리는 척일 뿐이다.
 * 진짜로 가리려면 링크가 브라우저에 아예 내려가지 않아야 한다. 그래서 서버가 판단한다.
 *
 * ── 데이터는 어디 있는가 ───────────────────────────────────────────────────
 * build_check.py 가 min_level > 1 인 항목을 `pd/<pd>/videos.private.json` 으로 뺀다.
 * 이 파일은 `/exam/.htaccess` 의 `<FilesMatch "\.(json|sql|md|...)$">` 가 **직접 조회를 막는다.**
 * 우리는 HTTP 가 아니라 파일시스템으로 읽으므로 그 차단과 무관하다.
 *
 * DB 를 쓰지 않는 이유: 영상 매핑은 빌드 산출물이고(youtube_map.json 이 원본),
 * 테이블·임포트 화면을 하나 더 만들 만큼의 데이터가 아니다. 파일 업로드에 같이 실려 온다.
 *
 * ⚠ 저자 검토용 링크(마이박스·드라이브)는 **그 자체가 접근 권한**이다.
 *   URL 을 아는 사람은 누구나 본다. 여기서 하는 일은 "URL 을 아는 사람을 줄이는 것"이고,
 *   외부 저장소의 공유 설정을 대신할 수는 없다.
 */
require_once __DIR__ . '/_boot.php';

$pd = ex_pd(isset($_GET['pd']) ? $_GET['pd'] : '', '');
if ($pd === '') ex_fail('pd_required');

// 품목 실재 확인 — 없는 이름으로 파일 경로를 만들지 않는다
$prod = sql_fetch("select pd_id from ex_product where pd_id = '" . sql_real_escape_string($pd) . "'");
if (!$prod) ex_fail('no_such_product', 404);

/* 내 레벨. 그누보드 기본값:
 *   1 비회원 · 2 일반회원 · … · 10 최고관리자
 * ⚠ 비로그인도 mb_level 이 1 이므로 로그인 판정에 쓰지 않는다(_boot.php ex_mb() 주석).
 *   여기서는 '레벨' 로만 쓰므로 비로그인 = 1 이 맞다.
 */
global $member;
$mb = ex_mb();
$level = ($mb !== '' && isset($member['mb_level'])) ? (int)$member['mb_level'] : 1;

/* ex_pd() 가 [a-z0-9-] 만 통과시키므로 경로 조작(../)이 불가능하다.
 * 그래도 basename 을 한 번 더 씌운다 — 검증 함수가 나중에 느슨해질 수 있다. */
$path = G5_PATH . '/exam/pd/' . basename($pd) . '/videos.private.json';

$out = new stdClass();
$hidden = 0;

if (is_readable($path)) {
    $raw = json_decode((string)file_get_contents($path), true);
    if (is_array($raw)) {
        $items = array();
        foreach ($raw as $round => $list) {
            if (!is_array($list)) continue;
            foreach ($list as $v) {
                $need = isset($v['min_level']) ? (int)$v['min_level'] : 0;
                if ($level < $need) { $hidden++; continue; }
                // min_level 은 내부 정보다. 화면에 필요 없으므로 내보내지 않는다.
                unset($v['min_level']);
                $items[$round][] = $v;
            }
        }
        if ($items) $out = $items;
    }
}

ex_out(array(
    'ok'     => 1,
    'pd'     => $pd,
    'level'  => $level,
    'items'  => $out,
    // 화면이 "레벨이 부족해 안 보이는 게 있다"를 알려줄 수 있게 개수만 준다.
    // 라벨·링크는 주지 않는다 — 그걸 주면 가린 의미가 없다.
    'hidden' => $hidden,
));
