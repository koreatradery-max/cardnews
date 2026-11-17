# STOCK PICK! 카드뉴스 자동화

3시간마다 이슈 3개를 골라 썸네일과 본문을 만들고, 텔레그램에서 승인하면 인스타그램에 올립니다.

## 흐름

1. **GitHub Actions** (3시간마다): 뉴스 수집 → 이슈 3개 선별(지난 7일간 다룬 이슈 제외) → 본문 작성 → 사진 후보 검색 → 썸네일 제작
2. 썸네일은 이 저장소의 `media` 브랜치에 올라갑니다 (최근 3일치만 유지).
3. **텔레그램**: 기존 봇이 관리자 DM으로 세트마다 `사진 + 본문 + [승인] [반려] [다른 사진]` 을 보냅니다.
4. **Cloudflare Worker** (기존 tg-login): 버튼을 처리합니다.
   - 승인 → 인스타그램 API로 게시 → 완료 알림(게시물 링크)
   - 반려 → 폐기
   - 다른 사진 → 같은 문구로 다음 사진 후보로 교체 (출처 표기도 함께 바뀜)

## 설정 (한 번만)

### 1. 저장소
- 이 폴더를 **공개(public)** 저장소로 올립니다. 인스타그램 API가 공개 주소의 이미지만 받기 때문입니다.
- Settings → Actions → General → Workflow permissions: **Read and write** 선택

### 2. GitHub Secrets (Settings → Secrets and variables → Actions)
| 이름 | 값 |
|---|---|
| `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` | developers.naver.com 에서 애플리케이션 등록 → 사용 API "검색" |

| `TELEGRAM_BOT_TOKEN` | 기존 봇 토큰 (Worker의 BOT_TOKEN 과 같은 값) |
| `TELEGRAM_ADMIN_CHAT_ID` | 승인 요청을 받을 텔레그램 숫자 ID (Worker의 ADMIN_TG_IDS 값) |

### 3. Cloudflare Worker (tg-login)
1. `worker/cardnews-worker.js` 전체를 worker 코드 맨 아래에 붙여 넣습니다.
2. 파일 머리말의 (1), (2) 두 군데를 고칩니다.
3. 환경 변수 추가: `IG_USER_ID`, `IG_ACCESS_TOKEN`(Secret), `CARDNEWS_BASE` = `https://raw.githubusercontent.com/<계정>/<저장소>/media/`
4. 배포 후 `https://<worker 주소>/setup?key=<WEBHOOK_SECRET>` 을 한 번 엽니다. (버튼 수신을 켜는 단계)

### 4. 인스타그램
- 계정을 **프로페셔널(비즈니스 또는 크리에이터)** 로 전환
- developers.facebook.com 에서 앱 생성 → Instagram 제품 추가 → "Instagram 로그인을 사용한 API 설정"
- 권한 `instagram_business_basic`, `instagram_business_content_publish` 로 액세스 토큰 생성
- 토큰과 계정 ID를 Worker 환경 변수에 넣습니다. 장기 토큰은 60일마다 갱신해야 합니다.

## 실행
- 자동: 한국 시간 0:07, 3:07, 6:07, 9:07, 12:07, 15:07, 18:07, 21:07
- 수동: Actions → "카드뉴스 자동화" → Run workflow
- 로컬 테스트(외부 호출 없이): `python -m tests.test_pipeline`, `node tests/test_worker.mjs`

## 바꿀 수 있는 값 (`cardnews/config.py`)
- `SETS_PER_RUN` 회차당 세트 수, `VARIANTS` 사진 후보 수, `HISTORY_DAYS` 중복 제외 기간
- `RSS_FEEDS`, `NAVER_SEED_QUERIES` 수집 채널
- `BRAND`, `CTA` 라벨과 마지막 줄 문구
- 문구 규칙은 `cardnews/write.py` 의 `SELECT_SYS`, `WRITE_SYS`

## 알아둘 점
- 사진은 기사 대표 이미지와 네이버 이미지 검색에서 가져오며, 본문 끝에 `📸 출처` 를 붙입니다. 출처를 적어도 저작권·초상권 문제가 될 수 있으니 승인 전에 사진을 확인하세요.
- 쓸 수 있는 사진이 없으면 글자만 있는 기본 배경으로 만듭니다.
- 글꼴은 Pretendard (SIL Open Font License) 입니다.
