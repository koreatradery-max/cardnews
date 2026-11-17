"""이슈 후보 수집: RSS(화제성) + 네이버 뉴스 검색 API(상세·보강)."""
import html, json, re, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from . import config

UA = {"User-Agent": "Mozilla/5.0 (compatible; cardnews-bot/1.0)"}


def http_get(url, headers=None, timeout=15, limit=3_000_000):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(limit), r.headers


def clean(s):
    s = re.sub(r"<[^>]+>", "", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def fetch_rss(category, url, limit=25):
    raw, _ = http_get(url)
    root = ET.fromstring(raw)
    items = []
    for it in root.iter("item"):
        title = clean(it.findtext("title"))
        if not title:
            continue
        src = clean(it.findtext("source")) or ""
        if src and title.endswith(" - " + src):          # 구글 뉴스는 제목 끝에 언론사명이 붙는다
            title = title[: -len(" - " + src)]
        items.append({"category": category, "title": title, "source": src,
                      "link": (it.findtext("link") or "").strip(), "desc": clean(it.findtext("description"))[:200]})
        if len(items) >= limit:
            break
    return items


def naver(kind, query, display=10, sort="sim"):
    """네이버 검색 API. kind: news | image"""
    if not (config.NAVER_ID and config.NAVER_SECRET):
        raise RuntimeError("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 이 설정되지 않았습니다.")
    q = urllib.parse.urlencode({"query": query, "display": display, "sort": sort})
    raw, _ = http_get(f"https://openapi.naver.com/v1/search/{kind}.json?{q}",
                      {"X-Naver-Client-Id": config.NAVER_ID, "X-Naver-Client-Secret": config.NAVER_SECRET})
    return json.loads(raw).get("items", [])


def naver_news(query, display=10, sort="sim"):
    out = []
    for it in naver("news", query, display, sort):
        link = it.get("originallink") or it.get("link") or ""
        out.append({"title": clean(it.get("title")), "desc": clean(it.get("description")), "link": link,
                    "naver_link": it.get("link") or "", "source": urllib.parse.urlparse(link).netloc.replace("www.", "")})
    return out


def collect_candidates(log=print):
    """화제 이슈 후보 목록. 제목 기준으로 중복을 걸러 최대 150건."""
    items = []
    for cat, url in config.RSS_FEEDS:
        try:
            got = fetch_rss(cat, url)
            items += got
            log(f"  RSS {cat} {len(got)}건  {url[:60]}")
        except Exception as e:
            log(f"  RSS 실패 {url[:60]} ({e})")
    for cat, q in config.NAVER_SEED_QUERIES:
        try:
            got = [{**n, "category": cat} for n in naver_news(q, 10, "date")]
            items += got
            log(f"  네이버 '{q}' {len(got)}건")
        except Exception as e:
            log(f"  네이버 실패 '{q}' ({e})")
    seen, uniq = set(), []
    for it in items:
        key = re.sub(r"[^0-9A-Za-z가-힣]", "", it["title"])[:18]
        if key and key not in seen:
            seen.add(key)
            uniq.append(it)
    return uniq[:150]


META = re.compile(r'<meta[^>]+(?:property|name)=["\']([^"\']+)["\'][^>]*content=["\']([^"\']*)["\']', re.I)
META2 = re.compile(r'<meta[^>]+content=["\']([^"\']*)["\'][^>]*(?:property|name)=["\']([^"\']+)["\']', re.I)


def fetch_article(url):
    """기사 페이지에서 본문 일부와 대표 이미지(og:image)를 뽑는다. 실패하면 빈 값."""
    try:
        raw, hdr = http_get(url, timeout=12, limit=1_500_000)
    except Exception:
        return {"text": "", "image": "", "site": ""}
    m = re.search(rb'charset=["\']?([\w-]+)', raw[:3000]) or re.search(r"charset=([\w-]+)", hdr.get("Content-Type", ""))
    enc = (m.group(1).decode() if m and isinstance(m.group(1), bytes) else (m.group(1) if m else "utf-8"))
    try:
        page = raw.decode(enc, "replace")
    except LookupError:
        page = raw.decode("utf-8", "replace")
    meta = {k.lower(): v for k, v in META.findall(page)}
    meta.update({k.lower(): v for v, k in META2.findall(page) if k.lower() not in meta})
    body = re.sub(r"(?is)<(script|style|noscript|header|footer|nav|aside|form)[^>]*>.*?</\1>", " ", page)
    paras = [clean(p) for p in re.findall(r"(?is)<p[^>]*>(.*?)</p>", body)]
    text = " ".join(p for p in paras if len(p) > 40)
    if len(text) < 200:                                    # <p> 를 안 쓰는 언론사: 태그를 지운 전체에서 긴 문장만
        text = " ".join(s for s in re.split(r"(?<=다\.)\s+", clean(body)) if 30 < len(s) < 300)
    return {"text": (clean(meta.get("og:description", "")) + " " + text)[:2500],
            "image": html.unescape(meta.get("og:image", "")), "site": clean(meta.get("og:site_name", ""))}
