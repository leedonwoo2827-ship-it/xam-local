<?php
if (!defined('_INDEX_')) define('_INDEX_', true);
if (!defined('_GNUBOARD_')) exit; // 개별 페이지 접근 불가

/**
 * theme/axexam/index.php — 그누보드 메인
 *
 * 우리 메인은 /exam/ 의 포털 랜딩이다. 그누보드 최신글 위젯 화면을 쓰지 않는다.
 * 루트는 .htaccess / index.php 리다이렉트로도 막고 있지만,
 * 그 둘이 어떤 이유로 안 걸려도 여기서 한 번 더 막는다(3중).
 *
 * ⚠ 나중에 그누보드 메인을 실제로 쓰게 되면 이 파일을 basic 의 index.php 로 되돌린다.
 */
header('Location: ' . G5_URL . '/exam/', true, 302);
exit;
