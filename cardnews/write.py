"""이슈 선별과 문구 작성 (Gemini API 무료 등급)."""
import json, re, time, urllib.error, urllib.request
from . import config


API = "https://generativelanguage.googleapis.com/v1beta"
_models = None


def _call(url, body=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None,
                                 headers={"x-goog-api-key": config.GEMINI_KEY, "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def model_order():
    """쓸 모델 순서. 무료 한도가 넉넉한 Flash-Lite 계열 최신 버전부터, 그다음 Flash 계열."""
    global _models
    if _models is None:
        if config.LLM_MODEL:
            _models = [config.LLM_MODEL]
        else:
            names = [m["name"].split("/")[-1] for m in _call(f"{API}/models?pageSize=200").get("models", [])
                     if "generateContent" in m.get("supportedGenerationMethods", [])]
            names = [n for n in names if n.startswith("gemini") and "flash" in n
                     and not re.search(r"image|tts|audio|live|embedding|preview|exp|thinking", n)]
            ver = lambda n: [int(x) for x in re.findall(r"\d+", n)[:2]] or [0]
            lite = sorted([n for n in names if "lite" in n], key=ver, reverse=True)
            full = sorted([n for n in names if "lite" not in n], key=ver, reverse=True)
            _models = (lite + full)[:6]
        if not _models:
            raise RuntimeError("사용할 수 있는 Gemini 모델을 찾지 못했습니다.")
    return _models


def llm(system, user, max_tokens=4096, image_jpeg=None):
    if not config.GEMINI_KEY:
        raise RuntimeError("GEMINI_API_KEY 가 설정되지 않았습니다.")
    parts = [{"text": user}]
    if image_jpeg:
        import base64
        parts.insert(0, {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(image_jpeg).decode()}})
    body = {"system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"temperature": 0.6, "maxOutputTokens": max_tokens, "responseMimeType": "application/json"}}
    last = None
    for model in list(model_order()):
        for attempt in range(2):
            try:
                data = _call(f"{API}/models/{model}:generateContent", body)
                parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
                text = "".join(p.get("text", "") for p in parts)
                if text.strip():
                    return text
                last = RuntimeError(f"{model}: 빈 응답")
                break
            except urllib.error.HTTPError as e:
                last = RuntimeError(f"{model}: HTTP {e.code} {e.read()[:200].decode('utf-8', 'replace')}")
                if e.code == 429 and attempt == 0:      # 분당 한도: 잠깐 쉬고 한 번 더
                    time.sleep(20)
                    continue
                break                                    # 한도 초과·모델 없음 → 다음 모델
    raise last or RuntimeError("LLM 호출 실패")


def parse_json(text):
    m = re.search(r"(\[.*\]|\{.*\})", text, re.S)
    if not m:
        raise ValueError("JSON 응답이 아님: " + text[:200])
    return json.loads(m.group(1))


SELECT_SYS = """너는 한국 인스타그램 이슈 매거진 계정의 에디터다. 뉴스 후보 목록에서 지금 가장 화제성이 큰 이슈를 고른다.
규칙:
- 카테고리: 대형 이슈·속보 / 정치·사회 / 기부·선행·감동 / 연예. 카테고리가 겹쳐도 되며 화제성만 본다.
- 유명인의 사건·사고(음주운전, 논란, 열애·결별 등)처럼 사람들이 많이 이야기하는 이슈도 좋다.
- 여러 언론사가 동시에 다루는 이슈일수록 화제성이 높다. 한 언론사만 보도한 이슈는 고르지 않는다.
- '이미 다룬 이슈'와 같은 사건은 절대 고르지 않는다. 후속 보도도 제외한다.
- 사망 사고의 잔혹한 묘사, 성범죄 피해자 신상, 미성년자 관련 선정적 이슈, 근거 없는 루머는 제외한다.
- 서로 다른 사건으로 요청한 개수만큼 화제성 순으로 고른다.
- 반드시 [기사 후보]에 있는 기사로 뒷받침되는 이슈만 고른다. [지금 화제]는 무엇이 크게 다뤄지는지 판단하는 참고용이다.
JSON 배열만 출력한다. 각 원소: {"topic": "사건을 한 문장으로", "category": "위 카테고리 중 하나", "query": "핵심 고유명사·단어 2~4개(공백 구분)", "articles": [이 이슈를 다룬 기사 후보 번호들, 최대 4개]}"""

WRITE_SYS = """너는 한국 인스타그램 이슈 카드뉴스 에디터다. 주어진 기사 자료만 근거로 카드뉴스 한 세트를 쓴다.
[썸네일 헤드라인]
- 2~3줄, 한 줄은 공백 포함 8~14자. 마침표 없이 끊는다.
- 첫 줄이 가장 눈에 띄어야 한다: 인용구("...") 또는 숫자·기록 표현(사상 첫, 역대 최고, 3,200만원)을 우선한다.
- 자료에 없는 내용, 과장, 낚시성 왜곡은 쓰지 않는다.
[본문]
- 반드시 첫 줄은 20자 안팎의 짧은 제목 한 줄로 시작한다 (헤드라인을 풀어 쓴 것, 마침표·이모지 없음). 그 뒤 빈 줄.
- 이어서 2~3개 문단, 문단마다 1~2문장, "~습니다"체. 문단 사이는 빈 줄.
- 자료에 있는 사실과 숫자만 쓴다. 추측·의견·평가·이모지·해시태그는 쓰지 않는다.
- 사람 이름과 직함은 자료에 적힌 표기 그대로 쓴다. 자료에서 그 사람의 직함이 확인되지 않으면 직함을 붙이지 않는다. 이름·직함·숫자를 기억이나 추측으로 채우지 않는다.
- 혐의·의혹 단계의 내용은 "~한 혐의를 받고 있습니다", "~라고 밝혔습니다"처럼 출처가 드러나게 쓴다.
- 전체 450자 이내.
JSON 객체만 출력한다: {"headline": ["줄1","줄2","줄3(선택)"], "caption": "본문", "ok": true}
자료가 부실해서 사실 확인이 안 되면 {"ok": false} 만 출력한다."""


def select_issues(candidates, trends, history_topics, n):
    lines = [f"{i+1}. [{c['category']}] {c['title']} ({c['source']})" for i, c in enumerate(candidates)]
    user = ("[이미 다룬 이슈]\n" + ("\n".join("- " + t for t in history_topics) or "- 없음") +
            "\n\n[지금 화제]\n" + ("\n".join("- " + t for t in trends) or "- 없음") +
            "\n\n[기사 후보]\n" + "\n".join(lines) + f"\n\n서로 다른 이슈 {n}개를 골라라.")
    out = []
    for p in parse_json(llm(SELECT_SYS, user)):
        if not (isinstance(p, dict) and p.get("topic") and p.get("query")):
            continue
        idx = [int(i) - 1 for i in p.get("articles", []) if str(i).isdigit() and 0 < int(i) <= len(candidates)]
        if idx:
            out.append({"topic": str(p["topic"]), "category": str(p.get("category", "")), "query": str(p["query"]),
                        "articles": [candidates[i] for i in idx[:4]]})
    return out


def write_set(issue, material):
    user = f"[이슈] {issue['topic']}\n[카테고리] {issue['category']}\n\n[기사 자료]\n" + material
    d = parse_json(llm(WRITE_SYS, user))
    if not d.get("ok", True) or not d.get("headline") or not d.get("caption"):
        return None
    return tidy(d)


VERIFY_SYS = """너는 뉴스 팩트체커다. 카드뉴스 초안의 모든 내용을 [기사 자료]와 한 문장씩 대조한다.
확인 대상: 사람 이름, 직함·소속, 숫자·금액·기간, 날짜·요일, 장소, 누가 무엇을 했는지, 인용구, 판결·처분 내용, 혐의인지 확정인지.
판정 기준:
- 자료에 같은 내용이 명시돼 있으면 근거 있음. 자료에 없거나, 자료와 다르거나, 여러 기사를 섞어 추정한 내용이면 근거 없음.
- 네가 알고 있는 배경지식은 근거가 아니다. 오직 [기사 자료]만 근거다.
- 혐의·의혹을 확정된 사실처럼 쓴 문장, 자료보다 과장한 헤드라인도 근거 없음으로 본다.
근거 없는 부분이 있으면 그 부분을 지우거나 자료 표현대로 고친 수정본을 만든다. 형식(헤드라인 2~3줄·한 줄 8~14자, 본문 첫 줄 짧은 제목 + 빈 줄 + 2~3문단, ~습니다체, 이모지 없음)은 유지한다.
이슈의 핵심 사실 자체가 자료로 확인되지 않으면 reject 한다.
JSON 객체만 출력한다: {"unsupported": ["근거 없는 내용 1", ...], "reject": false, "headline": ["줄1","줄2"], "caption": "본문(수정본 또는 원문 그대로)"}"""


def material_text(articles, bodies, extra_titles=()):
    mat = [f"- {a['title']} ({a['source']})" + (f": {a['desc']}" if a.get("desc") else "") for a in articles[:8]]
    mat += [f"- {t}" for t in extra_titles[:10]]
    for b in bodies:
        if b:
            mat.append("\n[기사 본문 발췌]\n" + b)
    return "\n".join(mat)


def numbers_ok(draft, material):
    """초안에 나온 숫자가 모두 기사 자료에 있는지 (쉼표 무시). 없는 숫자 목록을 돌려준다."""
    norm = lambda t: re.sub(r"(?<=\d),(?=\d)", "", t)
    src = norm(material)
    nums = set(re.findall(r"\d+(?:\.\d+)?", norm(" ".join(draft["headline"]) + " " + draft["caption"])))
    return sorted(n for n in nums if n not in src)


def tidy(draft):
    head = [re.sub(r"\s+", " ", str(h)).strip().rstrip(".") for h in draft.get("headline", []) if str(h).strip()][:3]
    cap = re.sub(r"\n{3,}", "\n\n", str(draft.get("caption", "")).strip())[:600]
    if len(head) < 2 or not cap:
        return None
    first = cap.split("\n", 1)[0].strip()
    if len(first) > 34 or first.endswith(("다.", "요.")):          # 첫 줄 제목이 빠졌으면 헤드라인으로 만든다
        cap = " ".join(h.strip('"“”') for h in head) + "\n\n" + cap
    return {"headline": head, "caption": cap}


def verify(draft, material):
    """AI 검수 1회. (수정본 또는 None, 근거 없는 내용 목록)"""
    user = ("[기사 자료]\n" + material + "\n\n[카드뉴스 초안]\n헤드라인: " + " / ".join(draft["headline"]) +
            "\n본문:\n" + draft["caption"])
    d = parse_json(llm(VERIFY_SYS, user))
    bad = [str(x) for x in d.get("unsupported", []) if str(x).strip()]
    if d.get("reject"):
        return None, bad or ["핵심 사실 확인 불가"]
    return tidy({"headline": d.get("headline") or draft["headline"], "caption": d.get("caption") or draft["caption"]}), bad


def double_check(draft, material, log=print):
    """2중 검증: ① AI 검수(근거 없는 내용 삭제·수정) → ② 수정본을 다시 검수해 문제 0건 + 숫자 자동 대조. 통과 못 하면 None."""
    fixed, bad = verify(draft, material)
    if fixed is None:
        log(f"   검증 탈락(1차): {bad}")
        return None, bad
    removed = list(bad)
    if bad:
        log(f"   1차 검수에서 수정: {bad}")
        fixed, bad2 = verify(fixed, material)
        if fixed is None or bad2:
            log(f"   검증 탈락(2차): {bad2}")
            return None, removed + bad2
    missing = numbers_ok(fixed, material)
    if missing:
        log(f"   검증 탈락(자료에 없는 숫자): {missing}")
        return None, removed + ["숫자 " + ", ".join(missing)]
    return fixed, removed


PHOTO_SYS = """너는 뉴스 사진 편집자다. 카드뉴스 기사와 사진이 맞는지 판정한다.
- 사진의 주인공이 기사에 나오지 않는 다른 인물(예: 기사는 캐나다 총리 회동인데 사진은 프랑스 대통령과 악수)이면 맞지 않음.
- 기사와 다른 행사·장소·사건 장면이 분명하면 맞지 않음.
- 기사 속 인물 단독 사진, 관련 장소·자료 사진, 상징적 사진처럼 기사와 어긋나지 않으면 맞음.
JSON 으로만 답한다: {"ok": true 또는 false, "why": "한 줄 이유"}"""


def photo_ok(img, headline, caption):
    """사진이 기사 내용과 맞는지 AI 로 확인. 판정 실패 시에는 통과시킨다."""
    import io
    buf = io.BytesIO()
    im = img.convert("RGB")
    im.thumbnail((768, 768))
    im.save(buf, "JPEG", quality=85)
    try:
        r = parse_json(llm(PHOTO_SYS, "[제목]\n" + " / ".join(headline) + "\n\n[본문]\n" + caption[:800], 300, buf.getvalue()))
        return bool(r.get("ok", True)), str(r.get("why", ""))
    except Exception as e:
        return True, f"판정 실패 {e}"
