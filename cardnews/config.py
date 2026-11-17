"""설정값. 비밀 키는 모두 환경변수(GitHub Secrets)에서 읽는다."""
import os
from datetime import timezone, timedelta

KST = timezone(timedelta(hours=9))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "out")
HISTORY = os.path.join(ROOT, "data", "history.json")
FONT_HEAD = os.path.join(ROOT, "fonts", "Pretendard-Black.otf")
FONT_SUB = os.path.join(ROOT, "fonts", "Pretendard-ExtraBold.otf")

BRAND = os.environ.get("CARDNEWS_BRAND", "STOCK PICK!")
CTA = os.environ.get("CARDNEWS_CTA", "팔로우하고 매일 이슈 받아보세요")
SETS_PER_RUN = int(os.environ.get("CARDNEWS_SETS", "3"))      # 1회 실행당 세트 수
VARIANTS = int(os.environ.get("CARDNEWS_VARIANTS", "3"))       # 이슈당 사진 후보 수
HISTORY_DAYS = 7                                               # 중복 제외 기간(일)

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
LLM_MODEL = os.environ.get("CARDNEWS_MODEL", "")               # 비우면 무료로 쓸 수 있는 Flash-Lite 계열을 자동 선택
WORKER_URL = os.environ.get("CARDNEWS_WORKER_URL", "").rstrip("/")   # 기존 텔레그램 Worker 주소
WORKER_KEY = os.environ.get("CARDNEWS_KEY", "")                # Worker 와 공유하는 비밀값
AUTO_APPROVE_MIN = float(os.environ.get("CARDNEWS_AUTO_MIN", "10"))  # 이 시간(분) 동안 응답이 없으면 자동 승인

# 기사 수집용 RSS (모두 무료·키 불필요, 기사 원문 주소를 직접 주는 피드). 실패한 피드는 건너뛴다.
RSS_FEEDS = [
    ("종합", "https://www.yna.co.kr/rss/news.xml"),
    ("정치", "https://www.yna.co.kr/rss/politics.xml"),
    ("사회", "https://www.yna.co.kr/rss/society.xml"),
    ("세계", "https://www.yna.co.kr/rss/international.xml"),
    ("연예", "https://www.yna.co.kr/rss/entertainment.xml"),
    ("연예", "https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=14&plink=RSSREADER"),
    ("종합", "https://news.sbs.co.kr/news/newsflashRssFeed.do?plink=RSSREADER"),
    ("속보", "https://www.newsis.com/RSS/sokbo.xml"),
    ("종합", "https://www.hani.co.kr/rss/"),
    ("종합", "https://www.khan.co.kr/rss/rssdata/total_news.xml"),
    ("종합", "https://www.kmib.co.kr/rss/data/kmibRssAll.xml"),
    ("종합", "https://www.mk.co.kr/rss/30000001/"),
    ("종합", "https://www.segye.com/Articles/RSSList/segye_recent.xml"),
    ("종합", "https://news-ex.jtbc.co.kr/v1/get/rss/issue"),
]
# 화제성 참고용 (구글 뉴스 주요 기사 제목. 링크는 쓰지 않고 "지금 많이 다뤄지는 이슈" 판단에만 쓴다)
TREND_FEEDS = [
    "https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko",
    "https://news.google.com/rss/headlines/section/topic/NATION?hl=ko&gl=KR&ceid=KR:ko",
    "https://news.google.com/rss/headlines/section/topic/WORLD?hl=ko&gl=KR&ceid=KR:ko",
    "https://news.google.com/rss/headlines/section/topic/ENTERTAINMENT?hl=ko&gl=KR&ceid=KR:ko",
]
# 기부·선행·감동 사연은 주요 기사에 잘 안 올라오므로, 제목에 이 단어가 있으면 [미담]으로 표시해 고르기 쉽게 한다
GOOD_NEWS_WORDS = ["기부", "선행", "미담", "쾌척", "익명", "성금", "장학금", "구조", "의인", "감동", "나눔"]
CATEGORIES = ["대형 이슈·속보", "정치·사회", "기부·선행·감동", "연예"]
