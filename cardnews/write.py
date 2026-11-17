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


def llm(system, user, max_tokens=4096):
    if not config.GEMINI_KEY:
        raise RuntimeError("GEMINI_API_KEY 가 설정되지 않았습니다.")
    body = {"system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
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
- 카테고리: 대형 이슈·속보 / 정치·사회 / 기부·선행·감동 / 연예. 가능한 한 서로 다른 카테고리에서 고른다.
- 여러 언론사가 동시에 다루는 이슈일수록 화제성이 높다.
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
- 첫 줄: 헤드라인을 한 문장으로 풀어 쓴 제목 (이모지 없음)
- 이어서 2~3개 문단, 문단마다 1~2문장, "~습니다"체. 문단 사이는 빈 줄.
- 자료에 있는 사실과 숫자만 쓴다. 추측·의견·평가·이모지·해시태그는 쓰지 않는다.
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


def write_set(issue, articles, bodies):
    mat = [f"- {a['title']} ({a['source']})" + (f": {a['desc']}" if a.get("desc") else "") for a in articles[:8]]
    for b in bodies:
        if b:
            mat.append("\n[기사 본문 발췌]\n" + b)
    user = f"[이슈] {issue['topic']}\n[카테고리] {issue['category']}\n\n[기사 자료]\n" + "\n".join(mat)
    d = parse_json(llm(WRITE_SYS, user))
    if not d.get("ok", True) or not d.get("headline") or not d.get("caption"):
        return None
    head = [re.sub(r"\s+", " ", str(h)).strip().rstrip(".") for h in d["headline"] if str(h).strip()][:3]
    cap = re.sub(r"\n{3,}", "\n\n", str(d["caption"]).strip())[:600]
    if len(head) < 2:
        return None
    return {"headline": head, "caption": cap}
