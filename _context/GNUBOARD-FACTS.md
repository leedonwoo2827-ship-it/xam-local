# 그누보드5 확장 지점 — 검증된 사실

작성 2026-07-29. 1차 근거는 전부 `github.com/gnuboard/gnuboard5` master(= **v5.6.34**, 2026-07-24 릴리스) 실제 소스로 확인. `sir.kr` 공식 매뉴얼은 자동 조회가 HTTP 403으로 차단되어 확인하지 못했고, 거기에 의존하는 항목은 모두 **확인 필요**로 표기했다.

이 문서의 목적: "그누보드에 붙이는 형태가 스킨인가 플러그인인가"에 대한 답과, 구현 중 참조할 코어 API 사실을 한곳에 모아두는 것.

---

## 결론 먼저

| 질문 | 답 |
|---|---|
| 스킨 / 플러그인 / 독립앱? | **독립 디렉터리 앱.** `plugin/`은 로딩 규격이 없고 스킨은 게시판 출력 슬롯일 뿐이다. 개발사 자신이 영카트(`shop/`)·관리자(`adm/`)·커뮤니티(`bbs/`)를 전부 "독립 디렉터리 + `../common.php` include"로 만들었다 |
| 훅 API 있나? | **있다.** `lib/hook.lib.php`의 `add_event`/`run_event`/`add_replace`/`run_replace` — 워드프레스 `add_action`/`add_filter` 동형 |
| OIDC 직접 구현? | **불필요.** 구글·카카오·네이버·페이스북·트위터·페이코가 코어 내장. **애플은 없다** |
| Q&A를 게시판으로? | **아니다. 커스텀 테이블 + 관리자 화면만 `adm/`** (§4) |
| 크레딧 원장에 `g5_point` 재사용? | **비추천.** 단 설계는 그대로 베껴라 (§5) |
| DB 접근 | **mysqli. PDO 없음.** 코어 테이블은 **MyISAM** |

---

## 1. `extend/` — 공식 확장 지점

**근거: `common.php` L836–853**

```php
// common.php 파일을 수정할 필요가 없도록 확장합니다.
$extend_file = array();
$tmp = dir(G5_EXTEND_PATH);
while ($entry = $tmp->read()) {
    // php 파일만 include 함
    if (preg_match("/(\.php)$/i", $entry))
        $extend_file[] = $entry;
}
if(!empty($extend_file) && is_array($extend_file)) {
    natsort($extend_file);
    foreach($extend_file as $file) {
        include_once(G5_EXTEND_PATH.'/'.$file);
    }
    unset($file);
}
```

- **파일명 규칙이 `*.extend.php`가 아니다.** 정규식은 `/(\.php)$/i` — `.php`로 끝나는 **모든** 파일. `.extend.php`는 관례일 뿐이고, 실제 배포본에도 `default.config.php`, `smarteditor_upload_extend.php`처럼 다른 형태가 있다.
- 로딩 순서는 **`natsort()`** — 파일명 자연순. 접두 숫자로 순서를 제어할 수 있다.
- 코어 소스의 이 주석(`// common.php 파일을 수정할 필요가 없도록 확장합니다.`)이 **그누보드5가 명문화한 "코어 수정 금지" 원칙**이다.

### include 시점 — `$member`·`$config`·DB 모두 살아있다

`common.php` 라인 순서:

| 라인 | 내용 |
|---|---|
| 13–14 | PHP 버전 게이트 (`5.2.17` 미만 die) |
| 135–136 | `$config = array();` / `$member = array(...)` 기본값 |
| **144** | **`include_once(G5_LIB_PATH.'/hook.lib.php');`** ← 훅 API가 extend보다 먼저 |
| 154–159 | `data/dbconfig.php` include → `sql_connect(...)` |
| 364 | `$config = get_config(true);` |
| 402/404 | `session_start()` |
| 535 | `$member = get_member($_SESSION['ss_mb_id']);` |
| 686–687 | `$is_member` / `$is_guest`, `$is_admin` |
| 788 | `define('G5_IS_MOBILE', $is_mobile);` |
| **838–853** | **`extend/` 로딩** |
| 873 | `run_event('common_header');` |

→ `extend/` 안에서 `$g5`, `$config`, `$member`, `$is_member`, `$is_admin`, DB 연결이 전부 사용 가능하다. **확정.**

### 한계

- **전역 함수 오버라이드는 불가.** PHP는 이미 정의된 함수를 재정의할 수 없고, `extend/`는 코어 lib 이후에 로드된다. 코어가 `if(!function_exists())`로 감싼 함수만 예외(함수별 개별 확인 필요). **오버라이드의 실제 수단은 `add_replace()` 훅이다.**
- L838보다 먼저 발화하는 훅(`get_config` L364, 자동로그인 관련)은 `extend/`에서 등록할 수 없다.

---

## 2. `plugin/` — 자동 로딩 없음. 하지만 훅은 있다

### `plugin/`은 서드파티 벤더 디렉터리다

실제 내용: `PHPMailer, browscap, debugbar, editor, htmlpurifier, inicert, jqplot, jquery-ui, kcaptcha, kcpcert, kcpcert_v2, lgxpay, okname, recaptcha, recaptcha_inv, sms5, sns, social, syndi`

매니페스트 파일도, 스캐너도, 활성/비활성 개념도 없다. 배선은 항상 `extend/`에서 한다 — 공식 예시 `extend/social_login.extend.php`:

```php
$g5['social_profile_table'] = G5_TABLE_PREFIX.'member_social_profiles';
define('G5_SOCIAL_LOGIN_DIR', 'social');
// ... G5_SOCIAL_USE_POPUP, G5_SOCIAL_CERTIFY_MAIL, G5_SOCIAL_IS_DEBUG, G5_SOCIAL_DELETE_DAY
include_once(... '/includes/functions.php');
```

→ **"플러그인 = `extend/`에 부트스트랩 1개 + `plugin/<이름>/`에 실제 코드"** 가 그누보드5의 사실상 플러그인 규약이다.

### 훅 API는 실재한다 — `lib/hook.lib.php`

| 함수 | 워드프레스 대응 |
|---|---|
| `add_event($tag, $func, $priority, $args)` | `add_action` |
| `run_event($tag, $arg)` | `do_action` |
| `add_replace($tag, $func, $priority, $args)` | `add_filter` |
| `run_replace($tag, $arg)` | `apply_filters` |
| `delete_event` / `delete_replace` / `get_hook_datas` | — |

소스에서 직접 확인한 태그 예: `common_header`(common.php L873), `admin_common`(adm/_common.php), `admin_amenu`/`admin_menu`(adm/admin.lib.php L771–773), `is_admin`(common.lib.php L1092), `insert_use_point_before`(L1279), `head_css_url`(head.sub.php L61/65), `qawrite_update`, `qa_delete`, `get_qa_config`, `html_purifier_config`, `html_purifier_result`.

**2차 정보 (비공식)**: [g5guide.github.io](https://g5guide.github.io/developers/hook.html)가 훅은 5.4(2019)부터라고 하며 [약 250개 태그 목록](https://g5guide.github.io/developers/hook-list.html)을 정리해 두었다. ⚠ 이 사이트는 **스스로 비공식임을 명시**한다("개발사가 안 만들어서 사용자가 직접 만드는 그누보드 안내서"). **공식 훅 목록 문서는 존재하지 않는다** — g5guide 자신도 코드에서 `run_event`/`run_replace`를 grep하라고 안내한다. 훅 도입 버전은 **확인 필요**.

---

## 3. 스킨과 독립앱

### 스킨은 모듈 출력 슬롯이다

`skin/` 하위 15개: `board, connect, content, faq, latest, member, new, outlogin, poll, popular, qa, search, shop, social, visit`

`skin/board/basic/list.skin.php` 실제 앞부분:

```php
<?php
if (!defined('_GNUBOARD_')) exit; // 개별 페이지 접근 불가

// 선택옵션으로 인해 셀합치기가 가변적으로 변함
$colspan = 5;
if ($is_checkbox) $colspan++;
if ($is_good) $colspan++;
if ($is_nogood) $colspan++;

// add_stylesheet('css 구문', 출력순서); 숫자가 작을 수록 먼저 출력됨
add_stylesheet('<link rel="stylesheet" href="'.$board_skin_url.'/style.css">', 0);
?>
```

받는 변수: `$board`, `$list`, `$write_pages`, `$is_admin`, `$is_category`/`$category_option`, `$is_checkbox`, `$is_good`/`$is_nogood`, `$width`, `$board_skin_url`, 검색·정렬 파라미터(`$sfl,$stx,$spt,$sca,$sst,$sod,$page`), 링크(`$write_href,$admin_href,$rss_href`).

PHP 로직은 넣을 수 있다(위 colspan 계산이 공식 예시). 하지만 스킨은 **부모 스코프에 include되는 템플릿**이고, 라우팅·권한·트랜잭션 문맥은 코어가 이미 정한 뒤다.

→ **문제풀이 SPA는 게시판 출력이 아니므로 스킨으로 만들면 안 된다.**

### 독립 디렉터리 + `common.php` include — 개발사 자신의 패턴

실제 파일 전문:

`bbs/_common.php` (278바이트):
```php
include_once('../common.php');
```

`bbs/_head.php` (110바이트):
```php
if (!defined('_GNUBOARD_')) exit; // 개별 페이지 접근 불가
include_once(G5_PATH.'/_head.php');
```

`adm/_common.php` (310바이트):
```php
define('G5_IS_ADMIN', true);
require_once '../common.php';
require_once G5_ADMIN_PATH . '/admin.lib.php';
if (function_exists('g5_check_data_htaccess')) { g5_check_data_htaccess(); }
if (isset($token)) { $token = @htmlspecialchars(strip_tags($token), ENT_QUOTES); }
run_event('admin_common');
```

일반 페이지 예 `bbs/faq.php`:
```php
include_once('./_common.php');
...
$g5['title'] = $fm['fm_subject'];
include_once('./_head.php');
... 본문 ...
include_once('./_tail.php');
```

→ `include_once('../common.php')` 후 `$member`, `$g5`, `$config`, `$g5['connect_db']`(mysqli 핸들)이 전부 살아있다. **확정.**

### 영카트는 플러프인이 아니다 — `shop/` 독립앱이다

`github.com/gnuboard/gnuboard5` **최상위에 `shop/` 디렉터리가 그냥 있다.** 같은 레포, 같은 릴리스.

증거:
- `version.php`가 둘 다 정의: `G5_GNUBOARD_VER = '5.6.34'`, `G5_YOUNGCART_VER = '5.4.5.5.1'`
- 릴리스명이 "그누보드(영카트) 5.6.34"
- 영카트 전용 구성: 루트 `shop.config.php`, `shop/_common.php`, `shop/shop.head.php`/`shop.tail.php`, `lib/shop.lib.php`·`shop.data.lib.php`·`shop.uri.lib.php`, `adm/admin.menu400.shop_1of2.php`+`admin.menu500.shop_2of2.php`, `extend/shop.extend.php`, `install/gnuboard5shop.sql`, `skin/shop/`
- `shop/index.php` 첫 줄: `include_once('./_common.php');` → `include_once(G5_SHOP_PATH.'/shop.head.php');` … 끝에 `shop.tail.php`

→ **영카트가 "그누보드 위에 얹은 독립 웹앱"의 레퍼런스 구현이다.** 우리가 하려는 것과 정확히 같은 구조. 이게 가장 강한 근거다.

### 레이아웃 통합 — JS 전역이 이미 주입된다

`head.sub.php` L73–86:
```php
var g5_url       = "<?php echo G5_URL ?>";
var g5_bbs_url   = "<?php echo G5_BBS_URL ?>";
var g5_is_member = "...";  var g5_is_admin = "...";
var g5_is_mobile = "...";  var g5_cookie_domain = "...";
var g5_shop_url  = "...";  var g5_admin_url = "...";
```

→ SPA에서 경로는 `g5_url + '/exam/api/...'`로 쓰면 된다. 상대경로 문제가 해결된다. PHP에서는 `G5_URL` / `G5_PATH` / `G5_JS_URL` / `G5_BBS_URL`.

`<title>` 생성(`head.sub.php`): `$g5_head_title = implode(' | ', array_filter(array($g5['title'], $config['cf_title'])));` + `strip_tags()`.

애셋 주입은 **`add_stylesheet($html, $order)` / `add_javascript($html, $order)`** (`lib/common.lib.php`). 태그를 그냥 박으면 그누보드의 출력 버퍼 후처리(`html_process_buffer`, `html_process_script_files`, `html_process_css_files` replace 훅)와 위치가 어긋날 수 있다.

---

## 4. 관리자 메뉴 추가 — 파일만 추가하면 된다

**근거: `adm/admin.lib.php` L751–774**

```php
// 가변 메뉴
unset($auth_menu); unset($menu); unset($amenu);
$tmp = dir(G5_ADMIN_PATH);
$menu_files = array();
while ($entry = $tmp->read()) {
    if (!preg_match('/^admin.menu([0-9]{3}).*\.php$/', $entry, $m)) {
        continue;  // 파일명이 menu 으로 시작하지 않으면 무시한다.
    }
    $amenu[$m[1]] = $entry;
    $menu_files[] = G5_ADMIN_PATH . '/' . $entry;
}
@asort($menu_files);
foreach ($menu_files as $file) { include_once $file; }
@ksort($amenu);

$amenu = run_replace('admin_amenu', $amenu);
if (isset($menu) && $menu) { $menu = run_replace('admin_menu', $menu); }
```

- **`adm/admin.menu600.exam.php` 같은 새 파일을 넣으면 자동 인식.** 기존 파일 수정 불필요.
- 배포본 `adm/`에는 `admin.menu100/200/300/400.shop_1of2/500.shop_2of2/900`만 있다 → **600·700·800이 비어 있다.** 새 파일명은 배포본에 없으니 덮어쓰기 업데이트에도 살아남는다.

메뉴 배열 형식(`admin.menu900.php`):
```php
$menu["menu900"] = array(
    array('900000', 'SMS 관리', G5_SMS5_ADMIN_URL.'/config.php', 'sms5'),
    array('900100', 'SMS 기본설정', G5_SMS5_ADMIN_URL.'/config.php', 'sms5_config'),
    array('900400', '전송내역-건별', G5_SMS5_ADMIN_URL.'/history_list.php', 'sms_history', 1),
);
```
첫 항목(`x00000`)이 그룹 헤더, 5번째 요소 `1`은 메뉴에서 숨김.

관리자 페이지 스켈레톤(`adm/point_list.php`):
```php
<?php
$sub_menu = "200200";
require_once './_common.php';
auth_check_menu($auth, $sub_menu, 'r');
$g5['title'] = '포인트관리';
require_once './admin.head.php';
// ... 본문 ...
require_once './admin.tail.php';
```

권한(`adm/admin.lib.php`):
```php
function auth_check_menu($auth, $sub_menu, $attr, $return = false) {
    $check_auth = isset($auth[$sub_menu]) ? $auth[$sub_menu] : '';
    return auth_check($check_auth, $attr, $return);
}
function auth_check($auth, $attr, $return = false) {
    global $is_admin;
    if ($is_admin == 'super') { return; }        // 최고관리자는 무조건 통과
    if (!trim($auth)) { /* '이 메뉴에는 접근 권한이 없습니다.' */ }
    // $attr('r'/'w'/'d')가 $auth 문자열에 있는지 검사
}
```

→ **최고관리자는 항상 통과.** 부관리자는 `관리권한`에서 메뉴 코드를 부여해야 한다(메뉴 배열에 등록해 두면 권한 부여 화면 드롭다운에 자동 노출).

⚠ **관리자 페이지 파일은 `adm/` 안에 고유 접두사로 두는 게 안전하다** (`adm/exam_qna_list.php`). `adm/` 밖에 두면 `require './_common.php'`(adm용)를 못 쓰고, `admin.head.php`가 상대 include를 쓰므로 다른 디렉터리에서 부르면 깨질 수 있다(**정확한 동작 확인 필요**).

---

## 5. DB 접근 — mysqli. PDO 없음

`config.php`: `define('G5_MYSQLI_USE', true);` / `G5_DB_CHARSET = 'utf8'` / `G5_DB_ENGINE = ''` / `G5_ESCAPE_FUNCTION = 'sql_escape_string'`

`lib/common.lib.php`의 모든 래퍼가 `if(function_exists('mysqli_*') && G5_MYSQLI_USE) { mysqli_* } else { mysql_* }` 패턴. **PDO는 어디에도 없다. prepared statement 래퍼도 없다.**

| 함수 | 위치 | 비고 |
|---|---|---|
| `sql_query($sql, $error=G5_DISPLAY_SQL_ERROR, $link=null)` | common.lib.php L1968 | UNION/`information_schema` 차단 필터 내장 |
| `sql_fetch($sql, $error=..., $link=null)` | L2105 | query+fetch 한 줄 |
| `sql_fetch_array($result)` | — | `mysqli_fetch_assoc` |
| **`sql_real_escape_string($str, $link=null)`** | **L2886** | `mysqli_real_escape_string` — **이걸 써라** |
| `sql_num_rows` / `sql_insert_id` / `sql_free_result` / `sql_error_info` | — | |
| `sql_escape_string($str)` | **common.php** | ⚠ 아래 |

### ⚠ `sql_escape_string()`은 사실상 `addslashes()`다

```php
function sql_escape_string($str)
{
    if(defined('G5_ESCAPE_PATTERN') && defined('G5_ESCAPE_REPLACE')) {
        $pattern = G5_ESCAPE_PATTERN; $replace = G5_ESCAPE_REPLACE;
        if($pattern) $str = preg_replace($pattern, $replace, $str);
    }
    $str = call_user_func('addslashes', $str);
    return $str;
}
```

기본 `G5_ESCAPE_FUNCTION`이 이것으로 지정돼 있다. **커넥션 charset을 모르는 이스케이프**다.

→ **우리 코드에서는 `sql_real_escape_string()`을 쓰고, 정수는 `(int)`로 캐스팅한다.**

### 커스텀 테이블명은 `extend/`에서 등록 — 공식 선례 있음

코어 테이블명 ~33개는 설치기가 `data/dbconfig.php`에 기록한다(`install/install_db.php`가 `write_prefix, config_table, member_table, point_table, qa_config_table, qa_content_table, social_profile_table, menu_table, ...` 생성).

**`dbconfig.php`는 건드리지 말고** `extend/`에서 등록한다 — `extend/social_login.extend.php`가 하는 방식 그대로:
```php
$g5['exam_qna_table']    = G5_TABLE_PREFIX.'exam_qna';
$g5['exam_credit_table'] = G5_TABLE_PREFIX.'exam_credit_lot';
```

### ⚠⚠ 엔진 문제 — 크레딧 원장 설계의 핵심

`install/gnuboard5.sql`과 `adm/sql_write.sql`이 전부 `ENGINE=MyISAM DEFAULT CHARSET=utf8`로 테이블을 만든다. **MyISAM은 트랜잭션이 없다.**

그누보드 자신이 이걸 인정하고 우회한다. `insert_point()` (common.lib.php L1207–1213) 소스 주석:

> 레이스 컨디션 방지: MyISAM은 트랜잭션을 지원하지 않으므로 MySQL named lock(GET_LOCK)으로 검증/INSERT 구간을 직렬화한다.

`insert_use_point()` L1283–1286:

> 레이스 컨디션 방지: 매 단계마다 가장 오래된 행 1개를 SELECT한 후 WHERE 절에 사전 검증 조건을 포함한 원자적 UPDATE로 차감한다. **affected_rows로 성공/실패를 판별하고 실패 시 재시도하므로 락 없이 무결성 보장.** (MyISAM/InnoDB 모두 호환, FOR UPDATE 불필요)

그리고 v5.6.27 릴리스노트에 실제로 **"주문 포인트 차감 Race Condition (Double Spend) 수정"** 이 올라와 있다.

→ **우리 크레딧 테이블은 `ENGINE=InnoDB`, `CHARSET=utf8mb4`로 직접 만들고, 차감은 `UPDATE ... WHERE lot_used + :cost <= lot_qty` + affected_rows 확인 방식으로 한다.** 이 패턴은 그누보드 코어가 이미 검증한 것이다.

`config.php` 주석: utf8mb4는 MySQL/MariaDB 5.5+ 필요. `G5_DB_ENGINE` 상수로 설치 시 엔진 변경 가능 — **실제 설치본의 엔진은 직접 확인해야 한다.**

---

## 6. CSRF·XSS — 함수는 있으나 한계를 알아야 한다

### `get_token()` / `check_token()` 존재 확정 (`lib/common.lib.php` L2578, L2592)

```php
function get_token()
{
    $key = _get_token_key();
    $secret = _get_token_secret();
    $time = time();
    $hmac = hash_hmac('sha256', $secret . '|csrf_token|' . $time, $key);
    return $time . '.' . $hmac;
}

// POST로 넘어온 토큰의 HMAC 및 만료 시간 검증. 기본 만료 7200초(2시간)
function check_token($expire = 7200)
{
    $token = isset($_POST['token']) ? $_POST['token'] : '';
    // '.' 분리 → 시간·HMAC
    if (abs(time() - $time) > $expire) { alert('토큰이 만료되었습니다...'); return false; }
    if ($hmac !== $expected) { alert('올바른 방법으로 이용해 주십시오.'); return false; }
    return true;
}
```

- 키: `G5_TOKEN_ENCRYPTION_KEY` 없으면 `G5_TABLE_PREFIX` fallback(`_get_token_key()` L2626) → **`G5_TOKEN_ENCRYPTION_KEY`를 반드시 랜덤값으로 설정해야 한다.** (정의 위치는 `config.php`에 없었음 → **확인 필요**, `data/dbconfig.php` 추정)

### ⚠ 한계 3개 — JSON API에서 그대로 쓰면 안 된다

1. **`$_POST['token']`만 읽는다.** GET/AJAX는 POST 바디에 실어야 한다.
2. **세션·폼별 nonce가 아니라 시각 기반 HMAC** → 2시간 동안 모든 폼에 재사용 가능. 결제·차감 같은 중요 액션은 별도 멱등키를 함께 써야 한다.
3. **실패 시 `alert()`(JS)를 출력한다.** JSON 엔드포인트에서 `check_token()`을 그대로 부르면 응답에 HTML/JS가 섞인다. → **JSON API에서는 HMAC 검증을 직접 재현하거나 `check_request_origin()`을 쓴다.**

`check_request_origin($redirect_url='')` L2708 — Origin/Referer 검증. 함께 쓰면 좋다.

### XSS

- `get_text($str, $html=0, $restore=false)` L1853 — `< > " '` 엔티티화
- `conv_content($content, $html, ...)` — `plugin/htmlpurifier`(HTMLPurifier) 경유 정화. 관련 훅: `html_purifier_config`, `html_purifier_result`, `html_purifier_safeiframes`

→ **LLM 초안은 신뢰할 수 없는 문자열로 취급한다.** 출력 시 `get_text()`(HTML 불허) 또는 `conv_content()`(HTML 허용 시). 그리고 모든 인클루드 파일 첫 줄에 `if (!defined('_GNUBOARD_')) exit;`.

---

## 7. 소셜 로그인 — 코어 내장 확정

- `plugin/social/` 존재: `_common.php, config.php, error.php, index.php, popup.php, register_member.php, register_member_update.php, unlink.php` + `Hybrid/`, `includes/`, `img/`
- **`plugin/social/Hybrid/Providers/` 실제 파일: `Facebook.php, Google.php, Kakao.php, Naver.php, Payco.php, Twitter.php`** — HybridAuth 라이브러리 기반
- **애플(Apple)은 없다.**
- `extend/social_login.extend.php`로 자동 배선
- 테이블 `g5_member_social_profiles` (`install/gnuboard5.sql`), `$g5['social_profile_table']`로 등록
- `skin/social/` 존재
- v5.6.32 릴리스노트: "Social login app registration link updates" → 현재도 유지보수 중

**2차 정보 (미검증)**: [velog](https://velog.io/@devuoon/그누보드-SNS로그인소셜로그인-설정하는-방법) / [gnustudy](https://gnustudy.com/bbs/board.php?bo_table=gnu_tip&wr_id=66)가 **5.3부터 기본 내장**, 설정 위치는 **관리자 → 기본환경설정**(네이버 Client ID/Secret, 카카오 REST API 키 + Redirect URI, 구글 승인된 리디렉션 URI)이라고 한다. `adm/config_form.php`가 112KB인 것과 일치하지만 **"어느 버전부터"와 정확한 화면 위치는 확인 필요**.

→ **OIDC를 직접 구현할 필요가 전혀 없다.** 애플 로그인만 필요하면 별도 모듈이 필요하고, 그때는 SIR 유료 플러그인([소셜로그인 플러그인](https://sir.kr/g5_plugin/1594), [v2](https://sir.kr/boards/g5_plugin/2213))이 있다 — 애플 지원 여부·가격 **확인 필요**.

---

## 8. Q&A: 게시판이냐 커스텀 테이블이냐

### `wr_1`~`wr_10` 실제 스키마 (`adm/sql_write.sql`)

```sql
CREATE TABLE `__TABLE_NAME__` (
  `wr_id` int(11) NOT NULL AUTO_INCREMENT,
  `wr_num` int(11) NOT NULL DEFAULT '0',
  `wr_reply` varchar(10) NOT NULL,
  `wr_parent` int(11) NOT NULL DEFAULT '0',
  `wr_is_comment` tinyint(4) NOT NULL DEFAULT '0',
  `wr_comment` int(11) NOT NULL DEFAULT '0',
  `wr_option` set('html1','html2','secret','mail') NOT NULL,
  `wr_subject` varchar(255) NOT NULL,
  `wr_content` text NOT NULL,
  `mb_id` varchar(20) NOT NULL,
  `wr_password` varchar(255) NOT NULL,
  ...
  `wr_1` varchar(255) NOT NULL,   -- wr_2 ~ wr_10 동일
  PRIMARY KEY (`wr_id`),
  KEY `wr_seo_title` (`wr_seo_title`),
  KEY `wr_num_reply_parent` (`wr_num`,`wr_reply`,`wr_parent`),
  KEY `wr_is_comment` (`wr_is_comment`,`wr_id`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8;
```

- **`wr_1`~`wr_10` 전부 `varchar(255) NOT NULL`, 인덱스 없음.**
- 상태값(`pending`/`draft_ready`/`approved`)은 `wr_1`에 넣을 수 있지만 **인덱스가 없어 관리자 대기 큐 쿼리가 풀스캔**이다.
- **LLM 초안은 `wr_1`~`wr_10`에 못 넣는다 (255바이트).** `wr_content`(text)를 쓰거나 댓글 행(`wr_is_comment=1`)에 넣거나 별도 테이블이 필요하다.

### 게시판을 쓰면 공짜로 얻는 것

`g5_board` 컬럼과 `bbs/*.php` 164개 파일로 확인: 목록/페이징/검색/정렬, 글쓰기·수정·삭제 폼, 첨부파일(`g5_board_file`, `bo_upload_level`), 위지윅 에디터, 레벨 권한(`bo_read_level`/`bo_write_level`/`bo_comment_level`/`bo_reply_level`), 공지(`bo_notice`), 추천(`bo_use_good`), 스크랩, 답변글, 댓글, 메일 알림, RSS, 썸네일, 최신글(`latest()`), 관리자 게시판 관리·글 이동/복사, 카테고리.

### 그런데 상태 기계를 끼워넣는 비용이 크다

게시판의 기본 흐름은 **"회원이 쓰면 즉시 노출"** 이다. `pending`/`draft_ready`는 노출돼선 안 되므로 다음을 전부 손봐야 한다:

- 목록 쿼리 필터(`bbs/board.php`) — 스킨은 `$list`를 받기만 하므로 스킨만으론 불가
- 최신글 `latest()`, 검색 `bbs/search.php`, RSS, `g5_board_new`
- 승인 전 알림 억제

→ **게시판이 주는 "공짜"의 상당 부분(목록/검색/최신글/RSS)을 다시 무력화해야 한다.** 남는 이득은 첨부·에디터·권한 정도다.

### 비밀글(`wr_option='secret'`)은 반쪽이다

접근 통제 실제 코드(`bbs/board.php`):
```php
if (strstr($write['wr_option'], "secret"))
{
    $is_owner = false;
    if ($write['wr_reply'] && $member['mb_id'])
    {
        $row = sql_fetch(" select mb_id from {$write_table} where wr_num='{$write['wr_num']}' and wr_reply='' and wr_is_comment=0 ");
        if ($row['mb_id'] === $member['mb_id']) $is_owner = true;
    }
    $ss_name = 'ss_secret_'.$bo_table.'_'.$write['wr_num'];
    if (!$is_owner) {
        if (!get_session($ss_name))
            goto_url(G5_BBS_URL.'/password.php?w=s&bo_table='.$bo_table.'&wr_id='.$wr_id.$qstr);
    }
    set_session($ss_name, TRUE);
}
```

`bbs/password.php` 우회 조건:
```php
if ($is_admin || (isset($write['mb_id']) && $write['mb_id'] && $member['mb_id'] == $write['mb_id']))
```

⚠ 한계 2개:
1. **비밀번호 기반 게이트**다. "내 것만 본다"가 아니라 "비번 아는 사람은 본다". 회원제에서는 개념 불일치.
2. **비밀글도 목록에는 나온다** — 제목이 보이고 자물쇠 아이콘이 붙는다. 목록 쿼리에 비밀글 제외 필터가 없다. (목록 쿼리 레벨 필터 부재는 **정밀 확인 필요**하나 자물쇠 아이콘 관행 자체가 "제목 노출"을 뜻한다.)

### 참고: 전용 1:1 문의 모듈이 이미 있다

- `bbs/qalist.php, qaview.php, qawrite.php, qawrite_update.php, qadelete.php, qadownload.php, qahead.php, qatail.php`
- 관리자: `adm/qa_config.php`(23KB), `adm/qa_config_update.php`
- 스킨: `skin/qa/`
- 테이블 `g5_qa_content`: **`qa_status` tinyint(4)**, `qa_parent`(답변=자식 행), `qa_category`, `qa_type`, `qa_email_recv`/`qa_sms_recv`, `qa_file1/2`, **`qa_1`~`qa_5` varchar(255)**, `qa_content` text
- 훅: `qawrite_update`, `qa_delete`, `get_qa_config`, `qa_content_head/tail`

`qa_status`가 이미 있고 답변이 부모/자식 행이며 1:1 문의는 설계상 본인만 열람이다 — 게시판보다 우리 상태 기계에 가깝다. **하지만 `qa_1`~`qa_5`도 255바이트이고, `qa_config` 전역 설정·이메일/SMS 알림·관리자 화면이 "1:1 문의" 의미론에 묶여 있어 크레딧 개념을 끼우기 어렵다.** 그리고 코어 업데이트가 이 테이블을 건드릴 수 있다.

### 결론 — 하이브리드

**Q&A 본체는 커스텀 테이블. 관리자 화면만 `adm/`에 추가.**

1. **LLM 초안이 `wr_1`~`wr_10`(255바이트)에 안 들어간다.** 별도 컬럼/테이블이 어차피 필요하다.
2. **상태 컬럼에 인덱스가 없다.** 관리자 대기 큐가 핵심 쿼리인데 이걸 위해 어차피 `ALTER TABLE`을 해야 한다 → "게시판 스키마를 그대로 쓴다"는 이점이 사라진다.
3. **승인 전 비노출을 만들려면 목록/검색/최신글/RSS를 전부 건드려야 한다.** 게시판의 공짜 이득 대부분을 상쇄한다.
4. **비밀글은 "내 질문은 나만 본다"를 절반만 만족한다.** 커스텀 테이블에서는 `WHERE mb_id = '$mb_id'` 한 줄이면 끝난다.
5. **커스텀 테이블은 InnoDB로 만들 수 있다.** 크레딧 차감과 질문 생성을 묶으려면 이게 필수다. `g5_write_*`는 MyISAM이다.
6. **잃는 것은 첨부와 에디터 정도**다. 객관식 질문에 파일 첨부가 필요 없다면 손실이 거의 없다.
7. **그러면서 회원제·로그인·소셜로그인·관리자 UI·관리권한·`adm/` 메뉴·CSRF 토큰은 전부 그누보드 것을 재사용한다** — 이게 그누보드를 쓰는 이유이고 하이브리드는 그걸 하나도 포기하지 않는다.

---

## 9. 크레딧 원장 — `g5_point` 재사용 비추천, 설계는 베껴라

### 재사용하면 안 되는 이유

- `cf_use_point`를 켜면 **회원가입/글쓰기 포인트가 함께 동작**한다(`cf_register_point`, `cf_write_point` 등 `g5_config`). 무료 크레딧이 새어나가므로 관련 설정 전부를 0으로 잠가야 한다.
- **`insert_point()`의 `$expire`는 `cf_point_term > 0`일 때만 반영된다** (`common.lib.php` L1228–1234):
```php
$po_expire_date = '9999-12-31';
if($config['cf_point_term'] > 0) {
    if($expire > 0)
        $po_expire_date = date('Y-m-d', strtotime('+'.($expire - 1).' days', G5_SERVER_TIME));
    else
        $po_expire_date = date('Y-m-d', strtotime('+'.($config['cf_point_term'] - 1).' days', G5_SERVER_TIME));
}
```
  즉 **전역 유효기간을 켜야 건별 기간 지정이 가능**하다.
- 포인트가 회원 마이페이지·게시판 등에 "포인트"로 노출되어 "질문 크레딧"과 의미가 섞인다.

### 하지만 설계는 검증된 원장 패턴이다 — 그대로 베낀다

| `g5_point` 컬럼 | 역할 |
|---|---|
| `po_point` / `po_use_point` | 발행량 / 그 행에서 소진된 양 → **부분 소진 가능** |
| `po_expired` / `po_expire_date` | 0=유효, 1=소멸. `9999-12-31`=무기한 |
| `po_rel_table`/`po_rel_id`/`po_rel_action` + `KEY index1` | **멱등키** — 중복 지급/차감 방지 |
| `po_mb_point` | 잔액 스냅샷(감사용) |
| 소진 순서 | `order by po_expire_date asc, po_id asc` = **FIFO, 만료 임박분 우선** (`insert_use_point()` L1287–1290) |
| `KEY index2 (po_expire_date)` | 만료 스캔용 |

우리 `ex_credit_lot` 설계가 이것과 동형이다.

---

## 10. 요구사항 (v5.6.34 기준)

### 버전 / PHP

최신 릴리스(GitHub API):

| 태그 | 발행일 |
|---|---|
| **v5.6.34** | **2026-07-24** |
| v5.6.33 | 2026-07-24 |
| v5.6.32 | 2026-07-14 |
| v5.6.31 | 2026-06-26 |
| v5.6.30 / v5.6.29 | 2026-06-16 |
| v5.6.28 / v5.6.27 | 2026-06-01 |

PHP 최소(코드상 유일한 강제 게이트) — `common.php` L13–14:
```php
if( version_compare( PHP_VERSION, '5.2.17' , '<' ) ){
    die(sprintf('PHP 5.2.17 or higher required. Your PHP version is %s', PHP_VERSION));
}
```

PHP 8 동작 근거:
- `common.php` L140: `if( version_compare( phpversion(), '8.0.0', '>=' ) ) { $g5 = array('title'=>''); }` — PHP 8 전용 분기가 실제로 있다
- `common.php` L109: `if (7.0 > (float)phpversion())` — `magic_quotes_gpc` 처리를 PHP 7 미만으로 한정
- 릴리스노트에 PHP 8 호환 수정 반복: v5.6.28 "SMS 모듈 Add/Add2 매개변수 기본값 보정 (PHP 8 호환)"

⚠ **"PHP 8.2/8.3까지 지원"이라는 공식 상한 선언은 찾지 못했다 → 확인 필요.** 커뮤니티 2차 정보가 서로 다르다([g5guide](https://g5guide.github.io/gnuboard/install.html): "PHP 7.2 이상 권장", [tlog.kr](https://tlog.kr/theme/tlog-new/html/gnubord5_6.php): "8.2까지 완벽 지원").

→ **실무 권고: PHP 8.1 또는 8.2.** 8.3/8.4는 공식 근거가 없으니 스테이징에서 `E_DEPRECATED` 포함 로그를 확인한 뒤 결정한다.

### MySQL / MariaDB

- **공식 최소 버전 선언 문서를 찾지 못했다 → 확인 필요.** 커뮤니티: MySQL 5.0 이상, 5.6/5.7 권장.
- `config.php` 주석: **utf8mb4는 MySQL/MariaDB 5.5+ 필요.** 기본은 `G5_DB_CHARSET = 'utf8'`.
- ⚠ **실무 함정:** 공식 설치 SQL이 `datetime NOT NULL DEFAULT '0000-00-00 00:00:00'`을 쓴다. **MySQL 5.7/8.0 기본 `sql_mode`(`STRICT_TRANS_TABLES`, `NO_ZERO_DATE`)에서 문제가 될 수 있다.** MariaDB 10.x가 실무상 안전한 선택. 정확한 호환 매트릭스는 **확인 필요**.
- ⚠ 기본 엔진이 **MyISAM** (§5).

### 필요 PHP 확장 — `install/library.check.php` 실제 체크 항목

| 구분 | 확장 | 그누보드 자체 설명 |
|---|---|---|
| **필수** | MySQL(mysqli) | "MySQL DB 연결에 필요합니다" |
| **필수** | JSON | "설치 전 DB 점검 응답 처리에 필요합니다" |
| **필수** | iconv **또는** mbstring | "문자열 인코딩 처리에 필요합니다" |
| 권장 | GD | "자동등록방지 문자와 썸네일 기능에 필요합니다" |
| 권장 | OpenSSL | "암호화, 외부 연동, 보안 통신 기능 사용 시 권장됩니다" |
| 권장 | **cURL** | **"외부 API, 결제, 소셜 연동 사용 시 권장됩니다"** |
| 권장 | Fileinfo | "업로드 파일의 MIME 타입 확인에 권장됩니다" |

버전 하한 검사는 없다(존재 여부만).

### 쓰기 권한

- **`data/` 쓰기 권한 필수.** `common.php` L154: `$dbconfig_file = G5_DATA_PATH.'/'.G5_DBCONFIG_FILE;` — 설치기가 DB 접속정보를 여기 생성한다. 첨부파일·썸네일·캐시·로그도 모두 `data/` 하위.
- `perms.sh`는 `data/`와 무관하다 — 결제 CLI 바이너리만 다룬다:
```
chmod 755 plugin/kcpcert/bin/ct_cli, ct_cli_x64
chmod 755 plugin/okname/bin/okname, okname_x64
chmod 755 shop/kcp/bin/pp_cli, pp_cli_x64   (shop 존재 시)
```
- **정확한 chmod 목록(707/777 여부)의 공식 근거는 찾지 못했다 → 확인 필요.** 커뮤니티 관행은 `data/` 707.
- **공유호스팅:** PHP-FPM 사용자와 파일 소유자가 같으면 755로 충분하고, 아니면 707이 필요하다. `adm/_common.php`에 `g5_check_data_htaccess()` 호출이 있어 `data/` 직접 접근 차단 `.htaccess`를 자동 점검한다 → **nginx 환경에서는 이 `.htaccess`가 무효이므로 서버 설정으로 `data/` 직접 접근을 직접 막아야 한다.**

### curl로 외부 API 호출 — 제약 전혀 없다

"PHP 게시판이면서 LLM 호출이 되나?"에 대한 근거 3개:

1. **그누보드 스스로 cURL을 "외부 API" 용도로 권장 항목에 명시**한다 — `install/library.check.php`: *"외부 API, 결제, 소셜 연동 사용 시 권장됩니다"*
2. **소셜 로그인이 이미 외부 OAuth 서버와 HTTP로 통신**한다 — `plugin/social/Hybrid`(HybridAuth)가 Google/Kakao/Naver 엔드포인트를 호출
3. **결제 모듈이 전부 외부 PG API 호출**이다 — v5.6.34 릴리스노트가 KG이니시스 INIpay PRO 주문 취소 흐름, 나이스페이먼츠 추가 등을 다룬다

그누보드는 그냥 PHP 애플리케이션이다. `curl_*`, `file_get_contents`, `stream_context_create` 다 된다. **LLM API를 `curl`로 부르는 데 그누보드가 개입하는 지점은 없다.** (호스팅사가 아웃바운드를 막는지는 별개 문제 — 확인 필요.)

---

## 11. 업데이트 안전한 커스터마이즈 — 6가지

핵심 근거는 코어 소스의 주석 자체다 (`common.php` L836): `// common.php 파일을 수정할 필요가 없도록 확장합니다.`

| # | 방법 | 근거 | 안전한 이유 |
|---|---|---|---|
| 1 | `extend/<내이름>.extend.php` | common.php L836–853 | 배포본에 없는 파일명 |
| 2 | `add_event()` / `add_replace()` (extend/에서 등록) | lib/hook.lib.php + L144가 L838보다 먼저 | 코어 파일 미수정 |
| 3 | `adm/admin.menu6xx.<내이름>.php` | adm/admin.lib.php L755–768 정규식 스캔 | 배포본은 100/200/300/400/500/900만 사용 |
| 4 | `adm/<고유접두사>_*.php` (예 `adm/exam_qna_list.php`) | `_common.php`+`auth_check_menu`+`admin.head.php` 패턴 | 배포본에 없는 파일명 |
| 5 | `skin/<모듈>/<내이름>/`, `theme/<내이름>/` | 스킨/테마 지정 구조 | 배포본에 없는 디렉터리명 |
| 6 | 독립 디렉터리 `/exam/` | 영카트 `shop/`과 동일 패턴 | 배포본에 없는 경로 |

**절대 수정 금지:** `common.php`, `config.php`, `lib/*.lib.php`, `bbs/*.php`, `adm/admin.*.php`(기존), 기본 스킨, `install/*`. v5.6.27 릴리스노트를 보면 보안 수정이 `lib/`·`bbs/`·`adm/`·`shop/` 전반에 걸쳐 있다. **코어를 포크하면 보안 패치를 받을 수 없다.**

**`data/dbconfig.php`도 손대지 않는다** — 설치기가 생성/갱신한다. 커스텀 테이블명은 `extend/`에서 등록(§5).

⚠ **공식 업데이트 절차 문서(덮어쓰기인지 전체 교체인지)는 확인하지 못했다 → 확인 필요.** 커뮤니티 관행은 "압축 덮어쓰기 + `data/`, `dbconfig.php` 보존"이다. 위 6가지는 어느 쪽이어도 안전한 편이지만, 만약 절차가 "`adm/` 전체 삭제 후 재배치"라면 #3·#4가 사라진다.

→ **사이트 전체를 git으로 버전관리하고 업데이트 전 `git status`로 내 파일을 확인하는 습관**이 문서 부재를 메우는 가장 확실한 방법이다.

---

## 12. 보안 이력 — "설치하고 방치"가 불가능한 스택

### 공개 CVE (2차 출처)

- **CVE-2022-44216** — 5.5.4/5.5.5: Insecure Permissions, **원 비밀번호 없이 모든 사용자 비밀번호 변경 가능** ([advisory](https://github.com/advisories/GHSA-ch8g-82wx-x73x))
- **CVE-2022-3963** — `faq.php` XSS, 5.5.8.2.1에서 수정 ([advisory](https://github.com/advisories/GHSA-57g7-92mv-gwwp))
- 5.5.5 이하: 취약한 암호화 알고리즘 → 민감정보 노출
- 5.5.16: `member_confirm.php`/`login.php`/`logout.php` Open Redirect
- ASEC 권고: 5.5.16 미만 업데이트 필요 ([ASEC](https://asec.ahnlab.com/en/79487/))
- 목록: [CVEdetails - Gnuboard5](https://www.cvedetails.com/product/57150/Gnuboard-Gnuboard5.html?vendor_id=20134)

### v5.6.27 한 릴리스에 담긴 취약점 수정 (공식 릴리스노트)

- ORDER BY `sst`/`sod` 화이트리스트 누락 **Blind SQL Injection**
- 모바일 상품목록 정렬 파라미터 **SQL Injection**
- 설치기 관리자 입력 **SQL Injection**
- 설치기 `g5_shop_prefix` **PHP 코드 인젝션**
- KCP CLI Windows 환경 **명령 인젝션(RCE)**
- 댓글 textarea **Stored XSS**, `alert()` JS 이스케이프 **Stored XSS**, PG return POST 키 **Reflected XSS**
- 관리자 엔드포인트 권한 검증 및 **CSRF 토큰 추가**
- 게시물 이동/복사 시 대상 게시판 **권한 검증 누락**
- 쿠폰 다운로드 **TOCTOU**, 주문 포인트 차감 **Double Spend**

### 릴리스 빈도

2026-06-01 ~ 07-24 약 8주에 **8개 릴리스.** 보안패치 다수.

→ **운영 결론:** ① GitHub 릴리스 알림(Watch → Releases only)을 켠다. ② 스테이징 + git으로 업데이트 절차를 반복 가능하게 만든다. ③ 코어를 절대 포크하지 않는다. ④ **우리 코드에도 같은 클래스의 취약점이 생긴다는 걸 전제한다** — 특히 정렬 파라미터 화이트리스트, 관리자 엔드포인트 CSRF, 크레딧 차감 원자성.

---

## 13. SPA 통합 함정 7가지

**1. jQuery 1.12.4 + jquery-migrate 1.4.1이 무조건 로드된다** — `head.sub.php` L90–91:
```php
add_javascript('<script src="'.G5_JS_URL.'/jquery-1.12.4.min.js"></script>', 0);
add_javascript('<script src="'.G5_JS_URL.'/jquery-migrate-1.4.1.min.js"></script>', 0);
```
추가로 `common.js`, `wrest.js`, `jquery.menu.js`, `placeholders.min.js`가 붙는다. → **SPA가 최신 jQuery를 다시 로드하면 전역 `$` 충돌.** 그누보드 head를 쓰는 페이지에선 jQuery를 다시 로드하지 말거나 `jQuery.noConflict(true)`로 격리한다.

**2. 상대경로 금지 — 이미 준비된 JS 전역을 쓴다.** `head.sub.php` L73–86이 `g5_url`, `g5_bbs_url`, `g5_is_member`, `g5_is_admin`, `g5_is_mobile`, `g5_admin_url`, `g5_cookie_domain`을 주입한다. JS에선 `g5_url + '/exam/api/qna.php'`.

**3. CSS/JS 주입은 `add_stylesheet()` / `add_javascript()`로.** 두 번째 인자가 출력 순서. 태그를 그냥 박으면 출력 버퍼 후처리와 위치가 어긋날 수 있다.

**4. 모바일 자동 분기.** `common.php` L788 `define('G5_IS_MOBILE', $is_mobile);` → 참이면 CSS가 `mobile.css`로, 경로가 `mobile/`로 갈린다(`head.sub.php` L65). **반응형 SPA 한 벌만 쓰려면 `config.php`의 device 설정을 확인하고 우리 디렉터리는 모바일 분기 없이 한 벌로 유지한다.** (정확한 우회 상수는 **확인 필요**.)

**5. `problems.js` 같은 대용량 전역 데이터는 캐시 무효화를 직접 한다.** 그누보드의 `G5_JS_VER`는 코어 JS에만 붙는다. `?ver=<파일 mtime>`을 직접 붙인다.

**6. 모든 PHP 인클루드 파일 첫 줄에 `if (!defined('_GNUBOARD_')) exit;`** — 공식 관례. `.htaccess`가 안 먹는 nginx에서 특히 중요.

**7. AJAX 엔드포인트는 `_common.php`만 include하고 `_head.php`는 절대 include하지 않는다** (HTML이 섞인다). POST + 토큰 검증 + `header('Content-Type: application/json')`. 단 **`check_token()`은 실패 시 `alert()`(JS)를 출력하므로 JSON 엔드포인트에서 그대로 쓰면 안 된다** (§6).

---

## 14. 확인 필요 목록

추측으로 채우지 않은 것들. 필요해지는 시점에 확인한다.

1. **sir.kr 공식 매뉴얼 전체** — `sir.kr/manual/g5/*`가 자동 조회에 HTTP 403. 브라우저로 직접 확인 필요.
2. 그누보드5의 **공식 PHP 지원 상한**(8.2? 8.3? 8.4?) 선언.
3. **MySQL/MariaDB 공식 최소 버전** 및 `sql_mode` 호환 매트릭스.
4. **설치 시 chmod가 필요한 디렉터리 공식 목록**(707/777 여부).
5. **공식 업데이트 절차** — 덮어쓰기인가 전체 교체인가. (§11 안전성의 전제)
6. **소셜 로그인 도입 버전**(커뮤니티는 5.3) 및 관리자 설정 화면 정확한 위치.
7. **훅 도입 버전**(커뮤니티는 5.4) 및 태그별 도입 버전 — 공식 훅 목록 문서 자체가 없음.
8. `extend/.htaccess`(12바이트) 내용.
9. `G5_TOKEN_ENCRYPTION_KEY` / `G5_COMMUNITY_USE` 정의 위치 (`config.php`에 없음, `data/dbconfig.php` 추정).
10. **비밀글이 목록 쿼리에서 제외되는지** — 목록 쿼리 레벨 정밀 확인.
11. `adm/admin.head.php`를 `adm/` 밖에서 include할 때 상대경로가 깨지는지.
12. `G5_IS_MOBILE` 분기의 정확한 우회 방법(device 설정 상수).
13. `sql_affected_rows()` 함수의 정확한 이름 — `insert_use_point()`가 affected_rows를 쓰므로 존재하나, 래퍼 함수명 확인 필요. 없으면 `mysqli_affected_rows($g5['connect_db'])`.
14. 그누보드5 신규 설치본의 **기본 콜레이션** — `ex_*`를 여기 맞춰야 `g5_member` 조인 시 collation 충돌이 없다.
15. SIR 유료 소셜로그인 플러그인의 애플 로그인 지원 여부·가격.

---

## 15. 배워야 할 것은 5개뿐이다

- `sql_query()` / `sql_fetch()` / **`sql_real_escape_string()`**
- `$member` / `$is_member` / `$is_admin`
- `get_token()` / `check_token()` (JSON API에서는 직접 검증)
- `_common.php` / `_head.php` / `_tail.php` include 패턴
- `$menu["menu6xx"]` 배열 형식

프레임워크 학습이 없다. 20년 전 PHP 지식으로 충분하다. **이것이 스킨·플러그인 방식보다 학습 부담이 낮은 이유이기도 하다** — 스킨은 "어떤 변수가 들어오는지"를 모듈별로 외워야 한다.

---

## 출처

**1차 (공식 소스, `github.com/gnuboard/gnuboard5` master = v5.6.34)**
- [레포 최상위](https://github.com/gnuboard/gnuboard5) · [common.php](https://github.com/gnuboard/gnuboard5/blob/master/common.php) · [config.php](https://github.com/gnuboard/gnuboard5/blob/master/config.php) · [version.php](https://github.com/gnuboard/gnuboard5/blob/master/version.php) · [_head.php](https://github.com/gnuboard/gnuboard5/blob/master/_head.php) · [head.sub.php](https://github.com/gnuboard/gnuboard5/blob/master/head.sub.php) · [perms.sh](https://github.com/gnuboard/gnuboard5/blob/master/perms.sh) · [SECURITY.md](https://github.com/gnuboard/gnuboard5/blob/master/SECURITY.md)
- [lib/hook.lib.php](https://github.com/gnuboard/gnuboard5/blob/master/lib/hook.lib.php) · [lib/common.lib.php](https://github.com/gnuboard/gnuboard5/blob/master/lib/common.lib.php) · [lib/](https://github.com/gnuboard/gnuboard5/tree/master/lib)
- [adm/admin.lib.php](https://github.com/gnuboard/gnuboard5/blob/master/adm/admin.lib.php) · [adm/_common.php](https://github.com/gnuboard/gnuboard5/blob/master/adm/_common.php) · [adm/admin.menu900.php](https://github.com/gnuboard/gnuboard5/blob/master/adm/admin.menu900.php) · [adm/point_list.php](https://github.com/gnuboard/gnuboard5/blob/master/adm/point_list.php) · [adm/sql_write.sql](https://github.com/gnuboard/gnuboard5/blob/master/adm/sql_write.sql) · [adm/](https://github.com/gnuboard/gnuboard5/tree/master/adm)
- [bbs/_common.php](https://github.com/gnuboard/gnuboard5/blob/master/bbs/_common.php) · [bbs/_head.php](https://github.com/gnuboard/gnuboard5/blob/master/bbs/_head.php) · [bbs/faq.php](https://github.com/gnuboard/gnuboard5/blob/master/bbs/faq.php) · [bbs/board.php](https://github.com/gnuboard/gnuboard5/blob/master/bbs/board.php) · [bbs/password.php](https://github.com/gnuboard/gnuboard5/blob/master/bbs/password.php) · [bbs/](https://github.com/gnuboard/gnuboard5/tree/master/bbs)
- [extend/](https://github.com/gnuboard/gnuboard5/tree/master/extend) · [extend/social_login.extend.php](https://github.com/gnuboard/gnuboard5/blob/master/extend/social_login.extend.php)
- [plugin/](https://github.com/gnuboard/gnuboard5/tree/master/plugin) · [plugin/social/Hybrid/Providers](https://github.com/gnuboard/gnuboard5/tree/master/plugin/social/Hybrid/Providers)
- [skin/](https://github.com/gnuboard/gnuboard5/tree/master/skin) · [skin/board/basic/list.skin.php](https://github.com/gnuboard/gnuboard5/blob/master/skin/board/basic/list.skin.php)
- [install/library.check.php](https://github.com/gnuboard/gnuboard5/blob/master/install/library.check.php) · [install/gnuboard5.sql](https://github.com/gnuboard/gnuboard5/blob/master/install/gnuboard5.sql) · [install/install_db.php](https://github.com/gnuboard/gnuboard5/blob/master/install/install_db.php)
- [shop/index.php](https://github.com/gnuboard/gnuboard5/blob/master/shop/index.php)
- [릴리스 목록](https://github.com/gnuboard/gnuboard5/releases) · [v5.6.34](https://github.com/gnuboard/gnuboard5/releases/tag/v5.6.34) · [v5.6.32](https://github.com/gnuboard/gnuboard5/releases/tag/v5.6.32) · [v5.6.27](https://github.com/gnuboard/gnuboard5/releases/tag/v5.6.27)

**2차 (커뮤니티, 비공식 — 검증 안 됨)**
- [g5guide 라이프사이클](https://g5guide.github.io/developers/lifecycle.html) · [g5guide Hook](https://g5guide.github.io/developers/hook.html) · [g5guide Hook 목록](https://g5guide.github.io/developers/hook-list.html) · [g5guide 설치](https://g5guide.github.io/gnuboard/install.html) · [g5guide 홈(비공식 명시)](https://g5guide.github.io/)
- [SIR 5.6.28 보안패치](https://sir.kr/boards/g5_pds/7648) · [tlog.kr 5/6 비교](https://tlog.kr/theme/tlog-new/html/gnubord5_6.php)
