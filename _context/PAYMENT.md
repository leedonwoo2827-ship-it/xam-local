# 결제 — 테스트부터 실결제까지

작성 2026-07-29. §1의 실측은 이 문서 작성 시점에 실제로 API를 호출해 확인한 것이다.

---

## 결론

**오늘 당장 가능하다.** 토스페이먼츠 공개 테스트 키로 **회원가입도 사업자등록도 없이** 빌링키 발급 → 1,100원 자동결제 승인까지 실제로 성공했다. 프로토타입 데모는 지금 만들 수 있다.

실결제는 사업자등록 + PG 계약 + **정기결제 별도 심사**가 필요하고, 초기 고정비 33만원이 있으므로 구독자 30명 이하 시점에는 계좌이체 수동 승인으로 버티는 게 맞다.

---

## 1. 실측 — 사업자등록 없이 빌링 전 플로우 성공

`https://api.tosspayments.com`에 실제 호출. 사용한 키는 그누보드5 공식 소스(v5.7.5 `subscription/settle_tosspayments.inc.php`)에 하드코딩된 **공개 테스트 키**다.

```
clientKey: test_ck_D5GePWvyJnrK0W0k6q8gLzN97Eoq
secretKey: test_sk_zXLkKEypNArWmo50nX3lmeaxYG5R
```

### ① 키 인증 확인 (대조군 포함)

```
GET /v1/payments/orders/nonexistent-...  → 404 NOT_FOUND_PAYMENT   ← 키 인증 성공
같은 요청, 가짜 키                        → 401 UNAUTHORIZED_KEY    ← 대조군
```

### ② 빌링키 발급 — 더미 카드번호로 성공

```
POST /v1/billing/authorizations/card
{"customerKey":"probe-c-3","cardNumber":"5365100000000000",
 "cardExpirationYear":"30","cardExpirationMonth":"12","customerIdentityNumber":"900101"}

→ HTTP 200
{"billingKey":"oLhh4twsoe3gyR5dZnl5bfVPyVNxHkUZvuP_cyWZ5MA=",
 "cardCompany":"카카오뱅크","mId":"tvivarepublica4"}
```

### ③ 그 빌링키로 1,100원 자동결제 승인 — 성공

```
POST /v1/billing/oLhh4twsoe3gyR5dZnl5bfVPyVNxHkUZvuP_cyWZ5MA=
{"customerKey":"probe-c-3","amount":1100,"orderId":"probe-order-sub-001",
 "orderName":"Question Pass Monthly"}

→ HTTP 200
{"status":"DONE", "type":"BILLING", "totalAmount":1100,
 "suppliedAmount":1000, "vat":100, "approvedAt":"2026-07-29T09:08:20+09:00",
 "receipt":{"url":"https://dashboard-sandbox.tosspayments.com/receipt/..."}}
```

**빌링키 발급 → 반복 승인 → 영수증 URL까지 전 플로우가 사업자등록 없이 동작한다.** 실제 돈은 나가지 않는다(`dashboard-sandbox`).

### 실측에서 걸린 함정 3개

1. **더미 카드번호는 앞 6자리 BIN이 유효해야 한다.**
   - `5365100000000000` (카카오뱅크) → **승인까지 통과** ✅
   - `4330...`, `4111...` → 빌링키는 발급되지만 **승인 단계에서 `NOT_SUPPORTED_CARD_TYPE` 실패**
   - `9430...` → `INVALID_CARD_NUMBER`
   - 토스 공식: *"테스트 환경에서는 카드 번호의 앞 여섯 자리(BIN 번호)만 유효해도 자동결제가 등록됩니다. 라이브 환경에서는 전체 카드 번호가 유효해야 합니다"*
   - **국내 전용 테스트 카드번호는 제공되지 않는다** — *"테스트용 국내 카드번호는 없어요"*
2. `orderId`는 **6~64자**, `customerKey`는 `-_=.@` 중 **특수문자 1개 이상 필수**.
3. billingKey 끝의 `=`는 URL 경로에 그대로 넣어도 동작한다.

### 근거

- *"회원가입이나 사업자 등록 없이도 토스페이먼츠의 온라인 결제를 테스트해볼 수 있다"* — [토스 API 테스트](https://docs.tosspayments.com/blog/how-to-test-toss-payments)
- 테스트 키는 `test`로 시작, *"실제 결제 정보(카드번호 등)를 사용할 수 있지만 승인은 가상으로 이뤄지고 금액이 출금되지 않는다"* — [API 키](https://docs.tosspayments.com/reference/using-api/api-keys)
- [자동결제(빌링) API 연동](https://docs.tosspayments.com/guides/v2/billing/integration-api)

### 테스트 모드 제약

- 금액 한도·기간 제한은 문서에 **명시 없음** → **확인 필요**
- 영수증 URL 미작동
- **카카오페이는 실계약 필요**
- 네이버페이 포인트/계좌 미작동

---

## 2. PG 업체별 — 오늘 테스트 가능 여부

| PG | 사업자등록 없이 오늘 테스트? | 회원가입 | 정기결제 테스트 | 근거 강도 |
|---|---|---|---|---|
| **토스페이먼츠** | **예** | **불필요** | **예 — 실측 성공** | ★★★ 실측 |
| 나이스페이먼츠 | 예 | 필요 (무료, 테스트상점 개설) | 예 — 샌드박스 빌키발급/승인 지원 | ★★☆ |
| NHN KCP | 예 | 불필요 (문서에 공개 코드) | 예 — 자동결제 테스트 사이트코드 공개 | ★★☆ |
| KG이니시스 | 예 | 불필요 (공개 테스트 MID) | 예 — 정기결제 전용 `INIBillTst` 공개 | ★★☆ |
| 포트원(PortOne) | 예 | 필요 (무료 가입) | 예 (V2 빌링키) | ★★☆ |
| 카카오페이 | **불확실 — 확인 필요** | — | 불확실 | ★☆☆ |

### 업체별 메모

**토스페이먼츠 — 1순위.** §1 참조. 실결제 제약: *"자동결제는 리스크 검토 및 추가 계약 후 사용할 수 있습니다"* — 테스트는 자유, **라이브 빌링은 별도 심사**.

**포트원.** *"관리자 페이지는 별도 계약없이 무료 회원가입이 가능"*, *"테스트 연동은 결제대행사와 계약 전에 미리 연동/개발이 가능한 테스트 연동환경"*. 여러 PG를 콘솔에서 스위치할 수 있어 **PG 선택을 미루고 싶을 때 유리**. 다만 추상화 레이어가 하나 더 끼므로 "1,100원 구독 하나 붙이기"에는 토스 직접 호출이 짧다. 주의: *"테스트MID로 간편결제 호출 시 테스트가 원활하지 않을 수 있습니다"*.

**나이스페이먼츠.** *"회원가입 후 로그인 하면 `테스트 상점 개설하기` 버튼이 활성화"*. 샌드박스에서 빌키발급/빌키승인 모두 지원. 제약: 부분취소 불가, 승인 응답이 임의 값. 그누보드5 소스의 공개 샌드박스 키(`S2_af4543a0be4d49a98122e01ec2059a56` / `9eb85607103646da9f9c02b128f2e5ee`, MID `nictest04m`)로 `sandbox-api.nicepay.co.kr` 인증 통과 확인. **가입 시 사업자등록번호 필수 여부 확인 필요.**

**NHN KCP.** 공식 문서에 테스트 값 공개: `site_cd: "T0000"`, `https://testsmpay.kcp.co.kr/trade/register.do`. 자동결제는 *"리스크 검토 및 별도 계약이 필요한 서비스"*. 그누보드5 소스의 자동결제 테스트 값: `site_cd A52Q7`, `group_id A52Q71000489`, `stg-spl.kcp.co.kr/gw/hub/v1/payment` + 테스트 인증서 전문.

**KG이니시스.** 일반결제 테스트 MID `INIpayTest`. **정기결제 전용 테스트 MID가 그누보드5 공식 소스에 공개**: MID `INIBillTst`, signkey `SU5JTElURV9UUklQTEVERVNfS0VZU1RS`, iniapi key `rKnPljRn5m6J9Mzz` / iv `W2KLNKra6Wxc1P==`, `https://stgstdpay.inicis.com/stdjs/INIStdPay.js`.

**⚠ 카카오페이 — 답이 흐리다.** 2차 출처들은 `TC0ONETIME`(단건) / `TCSUBSCRIP`(정기)를 테스트 CID로 언급하지만 **공식 문서에서 확인하지 못했다** (developers.kakaopay.com은 SPA라 본문 추출 불가). 오히려 공식 개발자 포럼에 미가맹 상태로 `TC0ONETIME` 호출 시 `invalid param(cid has invalid value)` 400이 나고 카카오 측이 명확히 답하지 않은 사례가 있다 ([forum/t/dev/309](https://developers.kakaopay.com/forum/t/dev/309)). 토스 문서도 *"카카오페이는 실계약 완료 필요"*라고 명시. → **프로토타입 1순위로 쓰지 않는다.**

---

## 3. 그누보드5 연동 — 5.7로 가면 안 된다

**중요한 발견: 그누보드5 코어에 정기결제 모듈이 실제로 존재하지만 안정 배포판(5.6.x)에는 없다.**

| | 5.6.34 (master, 최신 정식 릴리즈) | 5.7.5 |
|---|---|---|
| `shop/` 일반결제 모듈 | inicis, kcp, kakaopay, lg, naverpay, toss | 동일 |
| **`subscription/` 정기결제 모듈** | **없음** | **있음** |

`subscription/`에는 `settle_tosspayments.inc.php`, `settle_nicepay.inc.php`, `settle_kcp.inc.php`, `settle_inicis.inc.php`, `tosspayments/billing.php`(빌링키 발급), `cron_script.php`(주기 청구 배치), `mycard.php`(카드 관리)까지 완비돼 있다. 각 어댑터에 `su_card_test` 테스트 모드와 공개 테스트 키가 하드코딩돼 있다 — §1·§2에서 인용한 키들의 출처다.

### 5.7 라인을 쓰면 안 되는 이유

- `master` = **5.6.34**, 최신 정식 릴리즈(2026-07-24, prerelease=false). `subscription/` **없음**.
- `v5.7.5`는 **2025-09-23** 태그. GitHub Releases에 **5.7 릴리즈가 아예 없다.**
- `compare v5.7.5...master` → **`"status": "diverged"`, ahead_by 142 / behind_by 25.** 즉 5.7 라인은 master에 있는 **25개 커밋(보안 패치 포함)이 빠진 갈라진 브랜치**다.

→ **정기결제 때문에 5.7로 가는 건 보안 패치 라인을 버리는 트레이드오프다. 권장하지 않는다.**

SIR 서술도 일치한다: *"토스페이먼츠 정기결제 서비스는 영카트 5.7.4 이상 버전에서 지원"*, *"KG이니시스 정기결제 서비스는 영카트 5.7.0 이상 버전에서 지원"* ([tosspayments_pg.php](https://sir.kr/main/service/tosspayments_pg.php) / [inicis_pg.php](https://sir.kr/main/service/inicis_pg.php) — sir.kr이 403이라 검색 스니펫 기준 → **원문 확인 필요**. 단 소스코드로는 확실히 검증됨).

### 자체 `ex_order` + 토스 API 직접 호출 — 난이도 낮다

토스 빌링은 사실상 이게 전부다:

```php
// 1) 빌링키 발급 — 카드 등록 시 1회
POST /v1/billing/authorizations/card
Authorization: Basic base64(secretKey + ":")
{"customerKey": "<mb_id 기반 키>", "cardNumber": "...",
 "cardExpirationYear": "..", "cardExpirationMonth": "..",
 "customerIdentityNumber": "생년월일6자리"}
→ billingKey 저장 (customerKey ↔ mb_id 매핑)

// 2) 매달 청구 — cron 또는 로그인 시점 체크
POST /v1/billing/{billingKey}
Authorization: Basic base64(secretKey + ":")
{"customerKey": "...", "amount": 1100,
 "orderId": "<고유, 6~64자>", "orderName": "질문권 월정액"}
→ status == "DONE" 확인
```

PHP + cURL로 함수 두 개. 테이블은 `ex_order`(주문) + `ex_billing`(빌링키) + `ex_credit_lot`(질문권 잔액) 3개면 된다.

**영카트를 안 쓰는 게 오히려 유리하다** — 5.7 갈라진 라인을 피할 수 있고, "월 50개 지급 / 미사용분 소멸" 같은 커스텀 로직은 영카트 주문 모델에 억지로 끼우는 게 더 어렵다.

**유용한 활용: 5.7의 `subscription/settle_*.inc.php`를 참고 구현으로 읽는다.** 4개 PG의 빌링 호출 코드와 공개 테스트 키가 전부 들어 있는, 무료로 검증된 레퍼런스다. **파일만 읽고 5.7로 업그레이드는 하지 않는다.**

참고: 그누보드7에는 별도 플러그인 리포지토리가 있다 — `gnuboard/g7-plugin-sirsoft-tosspayments`, `g7-plugin-sirsoft-pay_nicepayments`, `g7-plugin-sirsoft-pay_nhnkcp`, `g7-plugin-sirsoft-pay_kginicis`.

### 스키마 (신규 1개, 기존 2개)

```sql
CREATE TABLE ex_billing (
  mb_id        VARCHAR(20)  NOT NULL PRIMARY KEY,   -- g5_member.mb_id
  customer_key VARCHAR(64)  NOT NULL,               -- 토스 customerKey (특수문자 1개 이상 필수)
  billing_key  VARCHAR(255) NOT NULL,               -- 토스 billingKey (끝에 = 포함 가능)
  card_company VARCHAR(40)  NOT NULL DEFAULT '',
  card_last4   CHAR(4)      NOT NULL DEFAULT '',
  pg           VARCHAR(16)  NOT NULL DEFAULT 'toss',
  is_test      TINYINT      NOT NULL DEFAULT 1,     -- 테스트 키로 발급된 것인지
  created_at   DATETIME     NOT NULL,
  updated_at   DATETIME     NOT NULL,
  UNIQUE KEY uq_ck (customer_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

`billing_key`는 **결제수단 그 자체**다. 유출되면 임의 청구가 가능하다. `ex_billing` 테이블 접근을 결제 코드로만 제한하고, 관리자 화면에도 `card_last4`만 표시한다.

`ex_order`는 `od_method`에 `pg_test` / `pg` / `bank` / `free`를 두면 테스트 → 실결제 전환이 값 변경으로 끝난다. `od_pg_tid`에 토스 `paymentKey`를 저장한다.

---

## 4. 수수료 — "건당 100원"은 공식 계약서로 반증됐다

### 원문 확인 결과

**토스페이먼츠 서비스 이용계약서 [개인사업자/신규] (2021-11-18 Ver.) p.2 「결제수단/수수료」 표**의 컬럼 구조:

| 결제수단 | 수수료 컬럼 형태 |
|---|---|
| 카드결제(신용/체크) | `%` **만** |
| 계좌이체 결제 | `%` **+ (최저수수료 ___원/건)** |
| 가상계좌 결제 | **`___원/건`** |
| 간편결제 | 원 결제수단과 동일 |
| **정기결제(빌링) → 카드결제** | **`%` 만 — 건당 고정 수수료 컬럼 없음** |
| 정기결제(빌링) → 휴대폰 | `%` 만 |
| 본인확인서비스 | `___원/시도 건` |

→ **정기결제 카드결제에는 건당 고정 수수료 항목이 존재하지 않는다.** "변동% + 건당 100원"이라는 2차 출처는 공식 계약서로 반증된다. **계좌이체의 최저수수료**(토스 공시: 2.0%, 최저 건당 200원) 또는 **CMS 자동이체**와 혼동된 것으로 보인다.

교차 확인: 스텝페이 스텝빌링 공시 = **PG 수수료 국내 1.7~3.4%**, 건당 고정 수수료 없음 ([steppay.kr/pricing](https://steppay.kr/pricing)).

⚠ 단 이용계약 **제42조 제3항**에 *"자동결제 수수료를 결제대금에서 선 공제"* 조항은 존재한다. 요율 자체는 상점관리자/별지에 기재되므로 **계약 시 "정기결제 카드결제 요율에 건당 고정액이 붙는지" 서면으로 못 박아야 한다.**

### 영세·중소 우대요율 — 두 개의 다른 숫자에 주의

| 출처 | 영세(3억↓) | 중소1 | 중소2 | 중소3 | 성격 |
|---|---|---|---|---|---|
| 토스 **이용계약서 p.2** 「영세 중소사업자 우대 수수료(카드결제만 해당)」 | **1.50%** | 2.00% | 2.10% | 2.20% | **PG 청구 기준. 우리에게 적용되는 숫자** |
| [토스 개발자센터 용어집](https://docs.tosspayments.com/resources/glossary/smm) | 0.40% (체크 0.15%) | 1.00% | 1.15% | 1.45% | **카드사 가맹점 수수료.** PG 마진 별도 |

계약서 각주가 **"(카드결제만 해당)"** 이고 표에서 `카드결제`와 `정기결제(빌링) 카드결제`는 별개 행이다. → **우대요율이 정기결제 행에도 적용되는지 확인 필요**(계약 시 명시 요청).

**신규 사업자는 처음에 일반요율(3.4%)** 이다. 여신금융협회가 **매년 1·7월** 재산정하고 영세 확인 시 **차액을 소급 환급**한다.

### 카카오페이 "영세가맹점 수수료 무료"는 오해다

- 2025년 정책은 상시 제도가 아니라 **명절 한시 이벤트**다: *"지난 9월 19일부터 10월 2일까지 약 2주간"* ([전자신문](https://www.etnews.com/20250930000275))
- 별건인 "신규 소상공인 가맹점 연말까지 면제"는 **신규 오프라인 결제 가맹점 대상, 카카오페이머니 기반 바코드·QR** ([파트너 공지](https://partner.kakaopay.com/help/notice/213))
- **온라인 정기결제 수수료 상시 면제는 어디에서도 확인되지 않는다.** 손익 계산의 전제로 쓰면 안 된다.

### 1,100원 1건 실효 수수료

1,100원 = 공급가액 1,000 + 부가세 100

| 케이스 | 요율 | 수수료(VAT포함) | 실입금 | 실효율 |
|---|---|---|---|---|
| 토스 **일반/신규** | 3.40% | **41원** | 1,059원 | **3.74%** |
| 토스 **영세 우대(계약서)** | 1.50% | **18원** | 1,082원 | **1.65%** |
| 스텝빌링 하단 | 1.70% | 21원 | 1,079원 | 1.87% |
| ~~건당 100원 가정~~ (반증됨) | 3.4%+100 | 151원 | 949원 | 13.7% |

**→ 수수료율만 보면 1,100원 월정액은 충분히 성립한다.**

---

## 5. 실결제 전환 요건 — 개인사업자 신규 기준

| 항목 | 내용 | 근거 |
|---|---|---|
| **사업자등록증** | **필수.** *"사업자등록과 쇼핑몰 제작을 완료한 사장님이라면 바로 신청 가능"* | [토스 블로그 semo-60](https://www.tosspayments.com/blog/articles/semo-60) |
| **정산계좌** | 필수. **개인사업자는 사업자명 또는 대표자명 계좌만. 타인 명의 불가** | 이용계약서 [개인사업자/신규] p.2 |
| **실제소유자 확인** | 특금법 제5조의2 / 시행령 제10조의5에 따라 대표자·실제소유자 성명·주민번호·국적 제출. **거부 시 계약 거절 가능** | 동 계약서 p.1 |
| **가입비 / 연관리비** | **가입비 220,000원(최초 1회) + 연관리비 110,000원(연 1회)**, 계약 형태에 따라 변동 | [토스 PG 수수료](https://www.tosspayments.com/about/fee) |
| **이행보증보험** | 계약 전 제출 필수. 보험가입금액은 예상 월 결제금액·업종·재무상태 고려. 예금질권·현금담보로 대체 가능. **신용도 우수 시 면제 가능** | 이용계약 제18조 |
| **심사 기간** | 접수 후 **3영업일** 내 계약부서 안내 메일 → **카드사 심사 약 2주** | [PortOne 헬프센터](https://help.portone.io/content/tosspayments-contract) |
| **정기결제 추가 심사** | **별도.** *"자동결제는 리스크 검토 및 추가 계약 후 사용할 수 있습니다"* / KCP도 *"리스크 검토 및 별도 계약이 필요한 서비스"* | 토스/KCP 공식 문서 |
| **정기결제 MID** | 기존 MID 뒤에 `_bill`을 붙여 자동 생성 | 이용계약서 p.2 각주 |
| **통신판매업 신고** | 사업자등록 **후** 정부24에서. **면제: 직전년도 통신판매 거래횟수 50회 미만 또는 부가세법상 간이과세자** | 공정위 「통신판매업 신고 면제 기준에 대한 고시」 |
| **구매안전서비스(에스크로) 확인증** | **예외에 전부 해당할 가능성 높음** ↓ | |

### 에스크로 — 예외 4개에 전부 걸린다

법제처 「찾기쉬운 생활법령정보」 기준 결제대금예치/소비자피해보상보험 의무의 **적용 제외**:

- **신용카드로 구매하는 거래**
- **배송이 필요하지 않은 재화등**(게임, 인터넷 학원 수강 등) / 정보통신망으로 전송되는 재화
- **10만원 미만 소액거래**
- **일정기간에 걸쳐 분할되어 공급되는 재화등**

→ 카드 정기결제 + 디지털 질문권 + 1,100원 + 월 분할 공급. **4개 전부 해당.** 다만 정부24 통신판매업 신고 실무에서 이용확인증을 요구하는 경우가 많으므로 **관할 시·군·구청 확인 필요.**

"월 50개씩 분할 지급, 이월 없음" 설계가 여기서 유리하게 작동한다 — *"일정기간에 걸쳐 분할되어 공급되는 재화등"* 에 정확히 부합한다.

### 정산·환불 기간

계약서 별지에 빈칸으로 협의: 정기결제(빌링) 카드결제는 `거래일(D) + (__)영업일`, 환불기간 `거래일(D) 기준 365일 이내`.

---

## 6. 회색지대 — 어디까지 해도 되는가

### ① 가상결제 UI만 두고 무료 베타 운영 — 문제 없다

실제 대가 수령이 없으면 과세 대상 거래가 없고 통신판매 행위 자체가 성립하지 않는다.

⚠ 단 소비자가 실제 결제로 오인하면 전자상거래법상 거짓·과장 표시 소지가 있다. **화면에 "테스트 결제 / 실제 청구되지 않습니다"를 명시한다.** (법률 판단은 **확인 필요** — 명문 규정으로 확인하지 못했다.)

### ② 무통장입금 수동 승인으로 실제 돈을 받으면 → 사업자등록 대상

국세청 기준은 **계속성·반복성·영리목적** 3요소이며 **결제수단과 무관**하다. *"계속적·반복적으로 판매하는 주체가 되면 규모와 무관하게 사업자등록을 해야 한다."* 계좌이체로 매달 1,100원을 반복 수취하면 정확히 이 요건이다.

- [국세청 사업자등록 안내](https://www.nts.go.kr/nts/cm/cntnts/cntntsView.do?mi=2443&cntntsId=7776)
- [한국세정신문 — 유튜버·SNS마켓, 판단기준은 '계속적·반복적이냐'](https://taxtimes.co.kr/mobile/article.html?no=245160)

### ③ 프로토타입 단계에서 소수 지인에게 무료 제공 — 문제 없다

대가를 받지 않으므로 재화·용역의 유상 공급이 아니고, 통신판매도 아니며, 사업자등록·통신판매업 신고 어느 것도 발생하지 않는다. **지금 있어야 할 자리다.**

(다만 "무료면 사업자등록 불필요"를 명시한 국세청 공식 문구는 확인하지 못했다 — 조문 해석에 근거한 결론이므로 애매하면 국세상담센터 **126**에 확인.)

### ⚠ 하지 말아야 할 것

사업자등록 전에 라이브 키로 실제 카드 결제를 받는 것. 애초에 **PG 계약 자체가 사업자등록증 없이는 불가**하므로 기술적으로도 막혀 있다.

---

## 7. 실행 순서

### 지금 (프로토타입 데모)

1. §1의 curl 3개를 그대로 실행 → **5분 안에 빌링 플로우 확인.** 아무 등록도 필요 없다.
2. `ex_billing` + `ex_order` + `ex_credit_lot` 3테이블 설계 (§3).
3. (선택) 토스 개발자센터 **이메일만으로 회원가입** → 전용 테스트 상점 키 + 테스트 결제내역 대시보드 + 웹훅 확보. 공식: *"전자결제 계약 전이어도 회원가입하면 나만의 테스트 상점 키를 확인하고 테스트 결제내역, 웹훅 등 기능을 사용할 수 있습니다."*
4. 데모 화면에 **"테스트 결제" 배지 고정.**
5. `subscription/settle_tosspayments.inc.php` + `subscription/tosspayments/billing.php` (v5.7.5)를 **참고 구현으로 읽기** — 파일만 참고하고 5.7로 업그레이드는 하지 않는다.

### 초기 운영 (구독자 30명 이하)

**계좌이체 수동 승인.** PG 가입비 33만원의 손익분기가 379건(구독자 32명 × 12개월)이므로 그 이전에 PG를 도입하면 회수하지 못한다. `ex_order.od_method='bank'` + `adm/exam_orders.php`에서 입금자명 대조 후 승인.

사업자등록은 병행 진행한다 — 계좌이체로 받아도 사업자등록 의무는 발생한다(§6-②).

### 실결제 전환 (구독자 30명 초과 후)

사업자등록 완료 → PG 신청 → **접수 3영업일 + 카드사 심사 2주 + 정기결제 별도 심사**를 일정에 반영. 테스트 키를 라이브 키로 바꾸고 `od_method`를 `pg_test` → `pg`로 바꾸는 것이 코드 변경의 전부다.

계약 시 서면으로 못 박을 것 3개:
1. 정기결제 카드결제 요율에 **건당 고정액이 붙는지**
2. **영세 우대요율(1.50%)이 정기결제 행에도 적용되는지**
3. 이행보증보험 요구 금액 (소액 시 면제 가능 여부)

---

## 8. 확인 필요 목록

1. 토스 테스트 모드의 **금액 한도·기간 제한** — 공식 문서에 명시 없음
2. **정기결제 카드결제에 건당 고정 수수료가 붙는지** — 계약서 표에는 컬럼 없음. 계약 시 서면 확인
3. **영세 우대요율(1.50%)이 정기결제(빌링) 행에도 적용되는지** — 각주가 "카드결제만 해당"으로 모호
4. 확인한 토스 이용계약서는 **2021-11-18 Ver.** 이고 **codemshop.com 호스팅**(토스 공식 도메인 아님). **현행판 요율 재확인 필요**
5. **카카오페이 테스트 CID(`TC0ONETIME`/`TCSUBSCRIP`) 미가맹 사용 가능 여부** — 공식 확인 실패, 포럼 사례는 부정적
6. **나이스페이 회원가입 시 사업자등록번호 필수 여부**
7. **SIR의 "영카트 5.7.x 정기결제 지원" 원문** — sir.kr 403. 단 소스코드로는 확실히 검증됨
8. **통신판매업 신고 시 에스크로 확인증 실제 면제 여부** — 관할 구청 확인
9. **간이과세자 부가세율** — 손익분기 379건 계산에 영향
10. 토스 **이행보증보험 실제 요구 금액** (개인사업자 신규, 소액 시 면제 가능성)

---

## 출처

**토스페이먼츠**
- [API 테스트 — 회원가입·사업자번호 없이 결제 테스트하기](https://docs.tosspayments.com/blog/how-to-test-toss-payments)
- [API 키](https://docs.tosspayments.com/reference/using-api/api-keys) · [자동결제(빌링) API 연동](https://docs.tosspayments.com/guides/v2/billing/integration-api) · [자동결제 결제창 연동](https://docs.tosspayments.com/guides/v2/billing/integration) · [코어 API 레퍼런스](https://docs.tosspayments.com/reference) · [영중소 수수료 용어집](https://docs.tosspayments.com/resources/glossary/smm)
- [PG 수수료](https://www.tosspayments.com/about/fee) · [전자결제서비스 이용계약](https://pages.tosspayments.com/terms/onboarding/) · [서비스 이용계약서 개인사업자/신규 PDF](https://www.codemshop.com/wp-content/uploads/pgall/tosspayment_individual.pdf) · [전자결제 신청 방법](https://www.tosspayments.com/blog/articles/semo-60)

**기타 PG**
- [PortOne 결제 연동 준비하기](https://developers.portone.io/opi/ko/integration/ready/readme) · [PortOne 토스페이먼츠 V2](https://developers.portone.io/opi/ko/integration/pg/v2/tosspayments) · [토스페이먼츠 상세 계약절차](https://help.portone.io/content/tosspayments-contract)
- [나이스페이먼츠 테스트 매뉴얼](https://github.com/nicepayments/nicepay-manual/blob/main/common/test.md) · [나이스페이 개발자센터](https://developers.nicepay.co.kr/)
- [NHN KCP 거래등록](https://developer.kcp.co.kr/reference/regist) · [NHN KCP 자동결제](https://developer.kcp.co.kr/guide/autopay)
- [카카오페이 개발자 포럼 — 미가맹 DEV 테스트](https://developers.kakaopay.com/forum/t/dev/309) · [카카오페이 파트너 공지 213](https://partner.kakaopay.com/help/notice/213) · [전자신문 — 영세 가맹점 수수료 무료 지원](https://www.etnews.com/20250930000275)
- [스텝페이 요금제](https://steppay.kr/pricing)

**그누보드**
- [gnuboard/gnuboard5 (subscription 모듈, 테스트 키)](https://github.com/gnuboard/gnuboard5) · [영카트5 매뉴얼 — KG 이니시스](https://sir.kr/manual/yc5/183) · [SIR 토스페이먼츠 PG](https://sir.kr/main/service/tosspayments_pg.php)

**법령**
- [찾기쉬운 생활법령정보 — 결제 관련 의무(에스크로 예외)](https://easylaw.go.kr/CSP/CnpClsMain.laf?popMenu=ov&csmSeq=25&ccfNo=3&cciNo=3&cnpClsNo=2) · [전자상거래법 전문](https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=282793) · [소비자24 — 통신판매업 신고면제기준](https://www.consumer.go.kr/user/bbs/consumer/380/940/bbsDataView/3579.do) · [정부24 통신판매업신고](https://www.gov.kr/mw/AA020InfoCappView.do?CappBizCD=11300000006&tp_seq=01)
- [국세청 사업자등록 안내](https://www.nts.go.kr/nts/cm/cntnts/cntntsView.do?mi=2443&cntntsId=7776) · [한국세정신문 — 계속적·반복적 판단기준](https://taxtimes.co.kr/mobile/article.html?no=245160)
