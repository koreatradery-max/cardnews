"""외부 호출을 모두 가짜로 바꿔 전체 흐름을 검증한다: python -m tests.test_pipeline"""
import io, json, os, random, shutil, sys, tempfile
from PIL import Image, ImageDraw, ImageFilter
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cardnews import config, collect, write, images, telegram
import run

tmp = tempfile.mkdtemp()
config.OUT_DIR = os.path.join(tmp, "out")
config.HISTORY = os.path.join(tmp, "history.json")
config.NAVER_ID = config.NAVER_SECRET = config.GEMINI_KEY = config.WORKER_KEY = "x"
config.WORKER_URL = "https://w.example"
config.AUTO_APPROVE_MIN = 0.001

TOPICS = [("올겨울 첫 한파특보 발효", "정치·사회", "한파특보 발효"), ("익명 기부자 1억원 전달", "기부·선행·감동", "익명 기부 1억원"),
          ("신인 그룹 데뷔 앨범 100만장", "연예", "신인 그룹 100만장"), ("지하철 요금 인상 확정", "정치·사회", "지하철 요금 인상"),
          ("국제 유가 급등", "대형 이슈·속보", "국제 유가 급등")]


def fake_img(seed, size=(1200, 800)):
    random.seed(seed)
    img = Image.new("RGB", size, (random.randint(20, 90), random.randint(20, 90), random.randint(40, 120)))
    d = ImageDraw.Draw(img)
    for _ in range(40):
        x, y, r = random.randint(0, size[0]), random.randint(0, size[1]), random.randint(30, 160)
        d.ellipse((x - r, y - r, x + r, y + r), fill=tuple(random.randint(60, 255) for _ in range(3)))
    b = io.BytesIO(); img.filter(ImageFilter.GaussianBlur(14)).save(b, "JPEG"); return b.getvalue()


def fake_get(url, headers=None, timeout=15, limit=0):
    if "rss" in url:
        items = "".join(f"<item><title>{t} - 가짜일보</title><link>https://ex.com/{i}</link><source>가짜일보</source></item>"
                        for i, t in enumerate([x[0] for x in TOPICS] + [f"채우기용 기사 제목 {k}번 소식" for k in "가나다라마바사아자차카타파하"]))
        return f"<rss><channel>{items}</channel></rss>".encode(), {}
    if "search/news" in url:
        return json.dumps({"items": [{"title": "<b>테스트</b> 기사", "description": "설명 &quot;인용&quot;", "originallink": f"https://press.example/{i}"} for i in range(5)]}).encode(), {}
    if "search/image" in url:
        return json.dumps({"items": [{"link": f"https://img.example/{i}.jpg"} for i in range(4)] + [{"link": "https://img.example/small.jpg"}]}).encode(), {}
    if "press.example" in url:
        return ('<html><head><meta charset="utf-8"><meta property="og:image" content="https://img.example/og%s.jpg">'
                '<meta property="og:site_name" content="가짜일보"></head><body><p>%s</p></body></html>' % (url[-1], "본문 문장입니다. " * 20)).encode(), {"Content-Type": "text/html"}
    if "small" in url:
        return fake_img(1, (300, 200)), {}
    if "img.example" in url:
        return fake_img(hash(url) % 1000), {}
    raise AssertionError(url)


calls = []
def fake_llm(system, user, max_tokens=0):
    calls.append(user)
    if "골라라" in user:
        return "```json\n" + json.dumps([{"topic": t, "category": c, "query": q} for t, c, q in TOPICS], ensure_ascii=False) + "\n```"
    return json.dumps({"ok": True, "headline": ['"이게 진짜 된다고?"', "역대 최고 기록 경신", "3시간마다 이슈 정리"],
                       "caption": "제목 한 줄입니다\n\n첫 문단입니다. 사실만 씁니다.\n\n둘째 문단입니다.", "image_queries": ["검색어1", "검색어2"]}, ensure_ascii=False)


collect.http_get = fake_get
write.llm = fake_llm
sent = []
telegram.worker = lambda path, payload, timeout=0: sent.append((path, payload)) or {"ok": True, "result": "sent"}

# 1회차: 3세트, 세트마다 사진 3장
made = run.generate()
assert len(made) == 3, made
for m in made:
    assert len(m["variants"]) == 3 and m["variants"][0]["credit"] == "가짜일보", m["variants"]
    for v in m["variants"]:
        im = Image.open(os.path.join(config.OUT_DIR, v["file"])); assert im.size == (1080, 1350)
assert made[0]["label"].startswith("[1/3]")
# 2회차: 앞의 3개는 중복이라 제외되고 남은 2개만 생성
made2 = run.generate()
assert [m["topic"] for m in made2] == [TOPICS[3][0], TOPICS[4][0]], [m["topic"] for m in made2]
# LLM 이 이미 다룬 이슈 목록을 받았는지
assert TOPICS[0][0] in calls[-3].split("[뉴스 후보]")[0]
# 텔레그램 전송 → 대기 → 자동 승인 확인 순서
run.notify()
assert [x[0] for x in sent] == ["/cardnews/submit"] * 2 + ["/cardnews/auto"] * 2, sent
assert sent[0][1]["id"] == made2[0]["id"]
# 사진이 하나도 없을 때 기본 배경
images.candidates = lambda *a, **k: []
it = run.build_set({"topic": "t", "category": "연예", "query": "q"}, "261117T0000-9")
assert it["variants"][0]["credit"] == config.BRAND
# 정리
open(os.path.join(config.OUT_DIR, "200101T0000-1_0.jpg"), "w").close()
run.prune(config.OUT_DIR, 72); assert not os.path.exists(os.path.join(config.OUT_DIR, "200101T0000-1_0.jpg"))
shutil.copy(os.path.join(config.OUT_DIR, made[0]["variants"][0]["file"]), "/home/claude/cardnews/test_render.jpg")
# Gemini 모델 자동 선택: Flash-Lite 최신 → Flash 순, 미리보기·이미지 모델 제외
write._models = None
write._call = lambda url, body=None: {"models": [{"name": "models/" + n, "supportedGenerationMethods": ["generateContent"]} for n in
    ["gemini-2.5-flash", "gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-3.1-flash-lite", "gemini-3.8-flash-image", "gemini-4.0-flash-lite-preview", "gemini-3.0-pro"]]}
assert write.model_order() == ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.8-flash", "gemini-2.5-flash"], write.model_order()
print("ALL OK")
