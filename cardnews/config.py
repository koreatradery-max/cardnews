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

NAVER_ID = os.environ.get("NAVER_CLIENT_ID", "")
NAVER_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
LLM_MODEL = os.environ.get("CARDNEWS_MODEL", "")               # 비우면 무료로 쓸 수 있는 Flash-Lite 계열을 자동 선택
WORKER_URL = os.environ.get("CARDNEWS_WORKER_URL", "").rstrip("/")   # 기존 텔레그램 Worker 주소
WORKER_KEY = os.environ.get("CARDNEWS_KEY", "")                # Worker 와 공유하는 비밀값
AUTO_APPROVE_MIN = float(os.environ.get("CARDNEWS_AUTO_MIN", "10"))  # 이 시간(분) 동안 응답이 없으면 자동 승인

# 화제성 수집용 RSS (키 불필요). 실패한 피드는 건너뛴다.
RSS_FEEDS = [
    ("종합", "https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko"),
    ("국내", "https://news.google.com/rss/headlines/section/topic/NATION?hl=ko&gl=KR&ceid=KR:ko"),
    ("세계", "https://news.google.com/rss/headlines/section/topic/WORLD?hl=ko&gl=KR&ceid=KR:ko"),
    ("연예", "https://news.google.com/rss/headlines/section/topic/ENTERTAINMENT?hl=ko&gl=KR&ceid=KR:ko"),
    ("종합", "https://www.yna.co.kr/rss/news.xml"),
    ("사회", "https://www.yna.co.kr/rss/society.xml"),
    ("정치", "https://www.yna.co.kr/rss/politics.xml"),
    ("연예", "https://www.yna.co.kr/rss/entertainment.xml"),
    ("세계", "https://www.yna.co.kr/rss/international.xml"),
]
# 네이버 뉴스 검색으로 보강할 카테고리 키워드 (기부·선행·감동 사연은 RSS 상위에 잘 안 올라오므로 직접 검색)
NAVER_SEED_QUERIES = [("속보", "속보"), ("미담", "기부 선행"), ("미담", "감동 사연"), ("연예", "연예 화제")]
CATEGORIES = ["대형 이슈·속보", "정치·사회", "기부·선행·감동", "연예"]
