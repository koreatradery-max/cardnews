# STOCK PICK! 카드뉴스 자동화

30분마다(한국 시간 03:00~05:00 제외) 이슈 1개를 골라 썸네일과 본문을 만들고, 승인 없이 바로 인스타그램·스레드에 올립니다. 텔레그램에는 기록용으로 함께 보냅니다. (민감 주제만 승인 대기)

## 흐름

1. **GitHub Actions** (3시간마다): 뉴스 수집 → 이슈 3개 선별(지난 7일간 다룬 이슈 제외) → 본문 작성 → 사진 후보 검색 → 썸네일 제작
   - **2중 검증**을 통과한 세트만 만듭니다.
     - ① 교차 확인: 서로 다른 언론사 2곳 이상이 보도한 이슈만 사용
     - ② AI 검수: 본문·헤드라인의 이름·직함·숫자·날짜를 기사 원문과 대조해 근거 없는 내용을 고치고, 다시 검수해 문제가 0건이어야 통과. 자료에 없는 숫자가 남으면 폐기
2. 썸네일은 이 저장소의 `media` 브랜치에 올라갑니다 (최근 3일치만 유지).
3. **텔레그램**: 기존 Worker(tg-login)의 봇이 관리자 DM으로 세트마다 `사진 + 본문 + [승인] [반려] [다른 사진]` 을 보냅니다.
4. **승인 처리** (Worker)
   - 승인 → 인스타그램 API로 게시 → 완료 알림(게시물 링크)
   - 반려 → 폐기
   - 이전 사진 / 다음 사진 → 같은 문구로 사진 후보를 앞뒤로 넘겨 봄 (출처 표기도 함께 바뀜)
   - 8~12시 회차는 10분 안에 응답이 없으면 자동 승인됩니다. 그 밖의 시간에는 승인한 것만 올라갑니다. (저장소 변수 `CARDNEWS_AUTO_WINDOW`, `CARDNEWS_AUTO_MIN` 으로 변경)

모두 무료 등급으로 동작합니다: GitHub Actions(공개 저장소), Gemini API 무료 등급, 언론사 RSS, Cloudflare Workers, 텔레그램, 인스타그램 API.

## 설정 (한 번만)

### 1. GitHub Secrets (Settings → Secrets and variables → Actions)
| 이름 | 값 |
|---|---|
| `GEMINI_API_KEY` | aistudio.google.com 에서 발급 (결제 수단 등록 없이 무료 등급 사용) |
| `CARDNEWS_KEY` | 직접 정한 긴 임의 문자열 (Worker 에도 같은 값) |
| `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` | 선택. 네이버 클라우드 NAVER API HUB 에서 Application 등록(뉴스·이미지 검색) 후 받는 값. 넣으면 관련 기사와 사진 후보가 늘고, 없어도 동작합니다. |

키가 등록되기 전에는 예약 실행이 아무 일도 하지 않고 끝납니다.

### 2. Cloudflare Worker (tg-login)
1. `worker/cardnews-worker.js` 전체를 worker 코드 맨 아래에 붙여 넣고, 파일 머리말의 (1)~(3) 세 군데를 고칩니다.
2. 환경 변수 추가
   - `CARDNEWS_KEY` (Secret): GitHub 의 CARDNEWS_KEY 와 같은 값
   - `CARDNEWS_BASE` (Text): `https://raw.githubusercontent.com/koreatradery-max/cardnews/media/`
   - `IG_USER_ID` (Text), `IG_ACCESS_TOKEN` (Secret)
3. 배포 후 `https://<worker 주소>/setup?key=<WEBHOOK_SECRET>` 을 한 번 엽니다. (버튼 수신을 켜는 단계)

### 3. 인스타그램
- 계정을 **프로페셔널(비즈니스 또는 크리에이터)** 로 전환
- developers.facebook.com 에서 앱 생성 → Instagram 제품 추가 → "Instagram 로그인을 사용한 API 설정"
- 권한 `instagram_business_basic`, `instagram_business_content_publish` 로 액세스 토큰 생성
- 장기 토큰은 60일마다 갱신해야 합니다. 만료되면 텔레그램으로 안내가 옵니다.

## 실행
- 자동: 한국 시간 8시~22시 매 정각 Cloudflare Worker 가 실행을 호출 (Worker 변수 `GH_DISPATCH_TOKEN` 필요. 운영 시간은 `CARDNEWS_START_HOUR`·`CARDNEWS_END_HOUR`, 간격은 `CARDNEWS_EVERY_HOURS` 로 변경)
- 수동: Actions → "카드뉴스 자동화" → Run workflow
- 로컬 테스트(외부 호출 없이): `python -m tests.test_pipeline`, `node tests/test_worker.mjs`

## 바꿀 수 있는 값 (`cardnews/config.py`)
- `AUTO_APPROVE_MIN` 자동 승인까지 기다리는 시간(분, 0이면 자동 승인 끔). 저장소 변수 `CARDNEWS_AUTO_MIN` 으로도 바꿀 수 있습니다.
- `SETS_PER_RUN` 회차당 세트 수, `VARIANTS` 사진 후보 수, `HISTORY_DAYS` 중복 제외 기간
- `RSS_FEEDS` 기사 수집 피드, `TREND_FEEDS` 화제성 참고 피드
- `BRAND`, `CTA` 라벨과 마지막 줄 문구
- 문구 규칙은 `cardnews/write.py` 의 `SELECT_SYS`, `WRITE_SYS`

## 알아둘 점
- 사진은 같은 이슈를 다룬 기사들의 대표 이미지에서 가져오며, 본문 끝에 `📸 출처` 를 붙입니다. 출처를 적어도 저작권·초상권 문제가 될 수 있으니 승인 전에 사진을 확인하세요.
- 쓸 수 있는 사진이 없으면 글자만 있는 기본 배경으로 만듭니다.
- 글꼴은 Pretendard (SIL Open Font License) 입니다.
