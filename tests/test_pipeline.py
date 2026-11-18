"""외부 호출을 모두 가짜로 바꿔 전체 흐름을 검증한다: python -m tests.test_pipeline"""
import io, json, os, random, shutil, sys, tempfile
from PIL import Image, ImageDraw, ImageFilter
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cardnews import config, collect, write, images, telegram
import run

tmp = tempfile.mkdtemp()
config.OUT_DIR = os.path.join(tmp, "out")
config.HISTORY = os.path.join(tmp, "history.json")
config.GEMINI_KEY = config.WORKER_KEY = "x"
config.WORKER_URL = "https://w.example"
config.AUTO_APPROVE_MIN = 0.001
config.AUTO_WINDOW = "0-23"

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
    if "rss/search" in url:
        import urllib.parse as up
        q = up.parse_qs(up.urlparse(url).query)["q"][0].replace(" when:2d", "")
        if "단독" in q:
            return b"<rss><channel></channel></rss>", {}
        return f"<rss><channel><item><title>{q} 관련 보도 - 다른신문</title><link>https://news.google.com/x</link><source>다른신문</source></item></channel></rss>".encode(), {}
    if "rss" in url.lower() or "google" in url:
        press = url.split("/")[2]
        titles = [x[0] for x in TOPICS] + [f"채우기용 기사 제목 {k}번 소식" for k in "가나다라마바사아자차카타파하"] + ["[부고] 아무개씨 별세"]
        items = "".join(f"<item><title>{t} {press[:3]}</title><link>https://press.example/{press}/{i}</link><description>설명 &quot;인용&quot;</description></item>"
                        for i, t in enumerate(titles))
        return f"<rss><channel>{items}</channel></rss>".encode(), {}
    if "press.example" in url:
        return ('<html><head><meta charset="utf-8"><meta property="og:image" content="https://img.example/%s.jpg">'
                '<meta property="og:site_name" content="가짜일보"></head><body><p>%s</p></body></html>' % (abs(hash(url)) % 9999, "본문 문장입니다. " * 20)).encode(), {"Content-Type": "text/html"}
    if "img.example" in url:
        return fake_img(hash(url) % 1000), {}
    raise AssertionError(url)


calls = []
def fake_llm(system, user, max_tokens=0):
    calls.append(user)
    if "골라라" in user:
        assert "[지금 화제]" in user and "부고" not in user.split("[기사 후보]")[1]
        return "```json\n" + json.dumps([{"topic": t, "category": c, "query": q, "articles": [i + 1]} for i, (t, c, q) in enumerate(TOPICS)], ensure_ascii=False) + "\n```"
    if "[카드뉴스 초안]" in user:
        cap = user.split("본문:\n", 1)[1]
        return json.dumps({"unsupported": [], "reject": False, "headline": user.split("헤드라인: ")[1].split("\n")[0].split(" / "), "caption": cap}, ensure_ascii=False)
    return json.dumps({"ok": True, "headline": ['"이게 진짜 된다고?"', "역대 최고 기록 경신", "매일 이슈 정리"],
                       "caption": "제목 한 줄입니다\n\n첫 문단입니다. 사실만 씁니다.\n\n둘째 문단입니다."}, ensure_ascii=False)


collect.http_get = fake_get
write.llm = fake_llm
sent = []
telegram.worker = lambda path, payload, timeout=0: sent.append((path, payload)) or {"ok": True, "result": "sent"}

# 1회차: 3세트, 세트마다 사진 3장
made = run.generate()
assert len(made) == 3, made
for m in made:
    assert len(m["variants"]) >= 1 and m["variants"][0]["credit"] == "가짜일보", m["variants"]
    for v in m["variants"]:
        im = Image.open(os.path.join(config.OUT_DIR, v["file"])); assert im.size == (1080, 1350)
assert made[0]["label"].startswith("[1/3]") and "검증: 언론사 2곳 보도 확인 · AI 검수 통과" in made[0]["label"]
assert made[0]["caption"].startswith("제목 한 줄입니다\n\n")
# 2회차: 앞의 3개는 중복이라 제외되고 남은 2개만 생성
made2 = run.generate()
assert [m["topic"] for m in made2] == [TOPICS[3][0], TOPICS[4][0]], [m["topic"] for m in made2]
# LLM 이 이미 다룬 이슈 목록을 받았는지
assert TOPICS[0][0] in [c for c in calls if "골라라" in c][-1].split("[지금 화제]")[0]
# 텔레그램 전송 → 대기 → 자동 승인 확인 순서
run.notify()
assert [x[0] for x in sent] == ["/cardnews/submit"] * 2 + ["/cardnews/auto"] * 2, sent
assert sent[0][1]["id"] == made2[0]["id"]
# 사진이 하나도 없을 때 기본 배경
# 네이버 키가 있으면 API HUB 주소·헤더로 호출하고, 관련 기사와 사진 후보가 추가된다
config.NAVER_ID, config.NAVER_SECRET = "id", "sec"
_get = collect.http_get
def nav_get(url, headers=None, timeout=15, limit=0):
    if "naverapihub.apigw.ntruss.com/search/v1/" in url:
        assert headers == {"X-NCP-APIGW-API-KEY-ID": "id", "X-NCP-APIGW-API-KEY": "sec"}, headers
        if "/news?" in url:
            return json.dumps({"items": [{"title": "<b>네이버</b> 기사", "description": "요약", "originallink": "https://press.example/nv/1", "link": "https://n.news.naver.com/x"}]}).encode(), {}
        assert "filter=large" in url
        return json.dumps({"items": [{"link": "https://img.example/nv1.jpg"}, {"link": "https://img.example/nv2.jpg"}]}).encode(), {}
    return _get(url, headers, timeout, limit)
collect.http_get = nav_get
it = run.build_set({"topic": "t", "category": "연예", "query": "큐큐 더블유", "articles": [{"title": "t", "link": "https://press.example/a/1", "source": "s", "desc": ""}]}, "261117T0000-8")
assert len(it["variants"]) == 3 and it["variants"][-1]["credit"] == "img.example", it["variants"]
config.NAVER_ID = ""
assert collect.naver_news("q") == [] and collect.naver_images("q") == []
images.candidates = lambda *a, **k: []
it = run.build_set({"topic": "t", "category": "연예", "query": "큐큐 더블유", "articles": [{"title": "t", "link": "https://press.example/a/1", "source": "s", "desc": ""}]}, "261117T0000-9")
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
# ---- 2중 검증
mat = "- 가수 A씨 음주운전 적발 (가짜일보)\n[기사 본문 발췌]\n경찰은 17일 A씨를 입건했다. 혈중알코올농도는 0.08%였다. 벌금 1,200만원."
good = {"headline": ["A씨 음주운전 적발", "혈중알코올 0.08%"], "caption": "A씨 음주운전 적발\n\n경찰은 17일 A씨를 입건했습니다. 벌금은 1200만원입니다."}
assert write.numbers_ok(good, mat) == []
assert write.numbers_ok({"headline": ["징역 3년 선고", "x"], "caption": "c"}, mat) == ["3"]
seq = []
def v_llm(system, user, max_tokens=0):
    seq.append(user); return json.dumps(replies.pop(0), ensure_ascii=False)
write.llm = v_llm
# 문제 없음 → 1회로 통과
replies = [{"unsupported": [], "reject": False, **good}]
t, fixed = write.double_check(good, mat, lambda *a: None); assert t and fixed == [] and len(seq) == 1
# 1차에서 수정 → 2차 재검수 통과
replies = [{"unsupported": ["직함 '국무총리'는 자료에 없음"], "reject": False, **good}, {"unsupported": [], "reject": False, **good}]
t, fixed = write.double_check(good, mat, lambda *a: None); assert t and len(fixed) == 1
# 2차에서도 문제 → 폐기
replies = [{"unsupported": ["a"], "reject": False, **good}, {"unsupported": ["b"], "reject": False, **good}]
assert write.double_check(good, mat, lambda *a: None)[0] is None
# 핵심 사실 확인 불가 → 폐기
replies = [{"unsupported": ["핵심"], "reject": True}]
assert write.double_check(good, mat, lambda *a: None)[0] is None
# AI 검수는 통과했지만 자료에 없는 숫자가 남음 → 폐기
bad = {"headline": ["징역 3년 선고", "A씨 음주운전"], "caption": good["caption"]}
replies = [{"unsupported": [], "reject": False, **bad}]
assert write.double_check(bad, mat, lambda *a: None)[0] is None
# 첫 줄 제목이 빠진 본문은 헤드라인으로 제목을 만든다
t = write.tidy({"headline": ['"재밌잖아요"', "집행유예 선고"], "caption": "서울 송파구에서 50대 남성이 현금을 뿌렸습니다. 경찰이 출동했습니다."})
assert t["caption"].startswith("재밌잖아요 집행유예 선고\n\n서울")
# 한 언론사만 보도한 이슈는 교차 확인에서 탈락
write.llm = fake_llm; collect.http_get = fake_get; config.NAVER_ID = ""
assert run.build_set({"topic": "t", "category": "연예", "query": "단독 보도", "articles": [{"title": "단독 보도", "link": "https://press.example/a/1", "source": "s", "desc": ""}]}, "261117T0000-7") is None
config.AUTO_WINDOW, config.AUTO_APPROVE_MIN = "8-12", 10
assert [config.auto_minutes(h) for h in (7, 8, 12, 13, 22)] == [0, 10, 10, 0, 0]
print("ALL OK")
