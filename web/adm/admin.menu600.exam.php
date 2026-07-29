<?php
if (!defined('_GNUBOARD_')) exit;

/**
 * 관리자 메뉴 등록 — 파일 추가만으로 끝난다. 코어 수정 0.
 *
 * 근거: adm/admin.lib.php L751~774 가 `/^admin.menu([0-9]{3}).*\.php$/` 로
 *       adm/ 를 스캔해 include 한다. 배포본은 100/200/300/400/500/900 만 쓰므로
 *       600 대역은 비어 있고, 이 파일명은 배포본에 없어서 코어 업데이트에도 살아남는다.
 *
 * 배열 형식: array(코드, 라벨, URL, 앵커ID[, 숨김])
 *   · 첫 항목 x00000 이 그룹 헤더
 *   · 5번째 요소 1 = 메뉴에서 숨김
 *
 * 권한: 최고관리자는 auth_check() 에서 무조건 통과한다.
 *       부관리자에게 주려면 여기 등록된 코드를 `관리권한` 화면에서 부여한다
 *       (등록해두면 권한 부여 드롭다운에 자동으로 뜬다).
 */

$menu['menu600'] = array(
    array('600000', '문제은행',    G5_ADMIN_URL.'/exam_import.php',       'exam'),
    array('600400', '문제 임포트', G5_ADMIN_URL.'/exam_import.php',       'exam_import'),

    // ↓ 아직 만들지 않았다. 해당 단계에서 주석을 푼다.
    //   메뉴에 먼저 올리면 404 링크가 되어 혼란스럽다.
    // array('600100', '대시보드',    G5_ADMIN_URL.'/exam_index.php',        'exam_index'),
    // array('600200', '질문 검수',   G5_ADMIN_URL.'/exam_qna_list.php',     'exam_qna'),
    // array('600300', '문제 목록',   G5_ADMIN_URL.'/exam_problem_list.php', 'exam_problem'),
    // array('600500', '질문권 지급', G5_ADMIN_URL.'/exam_credit_grant.php', 'exam_credit'),
    // array('600600', '주문 관리',   G5_ADMIN_URL.'/exam_orders.php',       'exam_orders'),
);
