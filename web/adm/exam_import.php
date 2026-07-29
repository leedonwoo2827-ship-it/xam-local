<?php
/**
 * 문제 임포트 — problems.json 업로드 → ex_problem upsert.
 *
 * phpMyAdmin 을 대체하는 화면이다. 이게 있어야 "로컬 재빌드 → SQL 붙여넣기" 마찰이 사라지고,
 * 오타·오답을 몇 분 안에 고칠 수 있다.
 *
 * 흐름:  python scripts/build_check.py --emit-json   →   여기에 업로드   →   버튼 한 번
 *
 * ⚠ 업로드된 파일은 처리 후 즉시 지운다. 웹루트에 problems.json 이 남으면
 *   문제 전체가 정적 파일로 노출된다(정답·해설이 공개라 치명적이진 않지만 둘 이유가 없다).
 */
$sub_menu = '600400';
require_once './_common.php';

auth_check_menu($auth, $sub_menu, 'r');

require_once G5_ADMIN_PATH . '/exam_lib/problem.php';

$report = null;
$fatal  = '';

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    auth_check_menu($auth, $sub_menu, 'w');

    /* ★ 관리자 영역은 check_token() 이 아니라 check_admin_token() 이다.
     *
     * 실측으로 확인한 것: adm/admin.js 가 관리자 영역의 **모든 submit 버튼을 가로챈다.**
     *   $(document).on("click", "form input:submit, form button:submit", ...)
     *   → adm/ajax.token.php 로 동기 AJAX → get_admin_token() 값을 받아
     *     input[name=token] 을 **덮어쓴다.**
     *
     * 그래서 서버에서 get_token() 으로 렌더해 넣어봐야 소용이 없다.
     * 제출 시점엔 관리자 토큰으로 바뀌어 있으므로 check_token() 은 반드시 실패한다
     * ("올바른 방법으로 이용해 주십시오").
     *
     * check_admin_token() 은 세션 ss_admin_token 과 대조하고 즉시 소거하는 1회용이다.
     * 코어 관리자 폼들이 token 필드를 value="" 로 비워두는 이유도 이것이다. */
    if (function_exists('check_admin_token')) {
        check_admin_token();
    } else {
        check_token();   // 아주 구버전 대비
    }

    $f = isset($_FILES['jsonfile']) ? $_FILES['jsonfile'] : null;

    if (!$f || $f['error'] !== UPLOAD_ERR_OK) {
        $codes = array(
            UPLOAD_ERR_INI_SIZE   => 'php.ini 의 upload_max_filesize 를 초과했습니다.',
            UPLOAD_ERR_FORM_SIZE  => '폼 지정 크기를 초과했습니다.',
            UPLOAD_ERR_PARTIAL    => '파일이 일부만 전송됐습니다. 다시 시도하십시오.',
            UPLOAD_ERR_NO_FILE    => '파일을 선택하지 않았습니다.',
            UPLOAD_ERR_NO_TMP_DIR => '서버에 임시 폴더가 없습니다.',
            UPLOAD_ERR_CANT_WRITE => '서버가 임시 파일을 쓰지 못했습니다.',
            UPLOAD_ERR_EXTENSION  => 'PHP 확장이 업로드를 막았습니다.',
        );
        $e = $f ? $f['error'] : UPLOAD_ERR_NO_FILE;
        $fatal = isset($codes[$e]) ? $codes[$e] : "업로드 실패 (코드 $e)";
        // 빈 POST = post_max_size 초과. PHP 가 $_FILES 를 통째로 비운다.
        if ($e === UPLOAD_ERR_NO_FILE && empty($_POST)) {
            $fatal = 'post_max_size(' . ini_get('post_max_size') . ')를 초과해 요청이 통째로 버려졌습니다. '
                   . 'build_check.py --emit-json --pd <품목> 으로 나눠 올리십시오.';
        }
    } else {
        $raw = file_get_contents($f['tmp_name']);
        @unlink($f['tmp_name']);          // ★ 즉시 삭제 — 웹루트에 남기지 않는다

        if ($raw === false || $raw === '') {
            $fatal = '업로드된 파일이 비어 있습니다.';
        } else {
            $doc = json_decode($raw, true);
            unset($raw);                   // 수 MB 를 메모리에 붙들고 있지 않는다
            if ($doc === null && json_last_error() !== JSON_ERROR_NONE) {
                $fatal = 'JSON 파싱 실패: ' . json_last_error_msg();
            } else {
                $report = ex_import_problems($doc, $member['mb_id']);
                unset($doc);
            }
        }
    }
}

$g5['title'] = '문제 임포트';
require_once './admin.head.php';
?>

<style>
.eximp{max-width:900px}
.eximp .box{background:#fff;border:1px solid #e3e6ec;border-radius:8px;padding:20px 22px;margin:0 0 18px}
.eximp h2{font-size:15px;margin:0 0 12px;font-weight:700}
.eximp .hint{color:#666;font-size:13px;line-height:1.7}
.eximp code{background:#f4f5f7;padding:1px 5px;border-radius:3px;font-family:Consolas,monospace}
.eximp pre{background:#0f172a;color:#e2e8f0;padding:12px 14px;border-radius:6px;overflow-x:auto;
  font-family:Consolas,monospace;font-size:12.5px;line-height:1.6}
.eximp .rep{border-collapse:collapse;width:100%;margin:0 0 10px}
.eximp .rep th,.eximp .rep td{border:1px solid #e3e6ec;padding:8px 12px;text-align:left;font-size:14px}
.eximp .rep th{background:#f7f8fa;width:180px;font-weight:600}
.eximp .n{font-weight:700;font-size:16px}
.eximp .ok{color:#0a7f3f}.eximp .warn{color:#b26a00}.eximp .bad{color:#c22638}
.eximp .msg{padding:12px 16px;border-radius:6px;margin:0 0 16px;font-size:14px;line-height:1.7}
.eximp .msg.err{background:#fdeced;border:1px solid #c22638;color:#8c1220}
.eximp .msg.good{background:#e9f7ef;border:1px solid #0a7f3f;color:#075c2d}
.eximp ul.keys{margin:8px 0 0 18px;font-size:13px;color:#555;max-height:200px;overflow:auto}
</style>

<div class="eximp">

<?php if ($fatal): ?>
  <div class="msg err"><b>임포트 실패</b><br><?php echo htmlspecialchars($fatal) ?></div>
<?php endif; ?>

<?php if ($report): ?>
  <?php if ($report['errors']): ?>
    <div class="msg err"><b>임포트 중단</b>
      <?php foreach ($report['errors'] as $e): ?><br><?php echo htmlspecialchars($e) ?><?php endforeach; ?>
    </div>
  <?php else: ?>
    <div class="msg good">
      <b>임포트 완료</b> — 품목 <code><?php echo htmlspecialchars($report['pd_id']) ?></code>,
      파일 안의 문제 <?php echo (int)$report['total'] ?>건
    </div>
  <?php endif; ?>

  <div class="box">
    <h2>임포트 결과</h2>
    <table class="rep">
      <tr><th>신규</th>
          <td class="n ok"><?php echo (int)$report['new'] ?>건</td></tr>
      <tr><th>갱신</th>
          <td class="n"><?php echo (int)$report['upd'] ?>건
            <span class="hint">— pr_hash 가 달라진 것만</span></td></tr>
      <tr><th>변경 없음</th>
          <td class="n"><?php echo (int)$report['skip_same'] ?>건
            <span class="hint">— 내용이 같아 건드리지 않음</span></td></tr>
      <tr><th>건너뜀 (웹 수정본)</th>
          <td class="n <?php echo $report['skip_edited'] ? 'warn' : '' ?>">
            <?php echo (int)$report['skip_edited'] ?>건
            <span class="hint">— <code>edited_by</code> 가 있어 덮어쓰지 않았다</span>
            <?php if ($report['edited_keys']): ?>
              <ul class="keys">
                <?php foreach ($report['edited_keys'] as $k): ?>
                  <li><?php echo htmlspecialchars($k) ?></li>
                <?php endforeach; ?>
              </ul>
              <div class="hint">원본으로 되돌리려면 문제 편집 화면에서 <b>원본 복원</b>을 누른 뒤
                다시 임포트한다.</div>
            <?php endif; ?>
          </td></tr>
      <tr><th>실패</th>
          <td class="n <?php echo $report['fail'] ? 'bad' : '' ?>"><?php echo (int)$report['fail'] ?>건</td></tr>
      <tr><th>회차 갱신</th>
          <td><?php echo (int)$report['rounds'] ?>행</td></tr>
    </table>

    <?php if ($report['warns']): ?>
      <div class="msg err" style="margin-top:12px"><b>행 단위 경고</b>
        <?php foreach (array_slice($report['warns'], 0, 30) as $w): ?>
          <br><?php echo htmlspecialchars($w) ?>
        <?php endforeach; ?>
        <?php if (count($report['warns']) > 30): ?>
          <br>… 외 <?php echo count($report['warns']) - 30 ?>건
        <?php endif; ?>
      </div>
    <?php endif; ?>
  </div>
<?php endif; ?>

  <div class="box">
    <h2>problems.json 업로드</h2>
    <form method="post" enctype="multipart/form-data">
      <?php /* value 를 비워둔다. adm/admin.js 가 submit 직전에 ajax.token.php 에서
               관리자 토큰을 받아 이 필드를 채운다. 코어 관리자 폼들(adm/auth_list.php,
               adm/board_form.php …)이 전부 value="" 인 이유다.
               서버에서 미리 채워 넣으면 어차피 덮어써진다. */ ?>
      <input type="hidden" name="token" value="">
      <p><input type="file" name="jsonfile" accept=".json,application/json" required></p>
      <p><input type="submit" value="임포트 실행" class="btn_submit"></p>
    </form>
    <div class="hint">
      서버 상한: <code>upload_max_filesize <?php echo ini_get('upload_max_filesize') ?></code> ·
      <code>post_max_size <?php echo ini_get('post_max_size') ?></code>
      (SQLD 300문제 ≈ 390KB)
    </div>
  </div>

  <div class="box">
    <h2>만드는 법</h2>
    <pre>python scripts/build_check.py --emit-json
# → D:\00work\ocr-output-260723\06\problems.json  (약 390KB)</pre>
    <div class="hint">
      빌드 리포트에 <b>과목 2종</b>이 찍히는지 먼저 확인한다.
      1종이면 <code>02/</code> 메타 조인이 깨진 것이고, 그대로 임포트하면
      <code>sj_name</code> 이 300건 전부 <code>"SQLD"</code> 로 들어가 재임포트해야 한다.
    </div>
  </div>

  <div class="box">
    <h2>동작 규칙</h2>
    <div class="hint">
      <b>pr_id 는 절대 바뀌지 않는다.</b> 기존 문제는 <code>UPDATE</code> 만 하고
      <code>DELETE + INSERT</code> 를 하지 않는다 —
      <code>ex_attempt_item</code>·<code>ex_wrong</code> 이 <code>pr_id</code> 를 참조하므로
      값이 갈리면 회원의 오답노트와 정답률 집계가 통째로 끊긴다.
      upsert 축은 <code>UNIQUE (pd_id, pr_key)</code> 이고
      <code>pr_key</code> 형식은 <code>m01-1#7</code> 이다.<br><br>

      <b>웹에서 고친 문제는 덮어쓰지 않는다.</b>
      <code>edited_by</code> 가 채워진 행은 건너뛰고 위 목록에 보고한다.<br><br>

      <b><code>pr_open</code> 은 임포트가 건드리지 않는다.</b>
      오류 신고로 숨긴 문제를 재임포트가 되살리면 안 된다.
      <code>rd_free</code>·<code>rd_open</code> 도 같은 이유로 보존한다.<br><br>

      ⚠ <b>웹 수정본은 <code>02/</code> 원본과 어긋난 채로 남는다.</b>
      주기적으로 <code>D:\00work\ocr-output-260723\02\</code> 로 역반영하지 않으면
      언제든 "원본 복원"이 낡은 내용을 되살린다.
    </div>
  </div>

</div>

<?php
require_once './admin.tail.php';
