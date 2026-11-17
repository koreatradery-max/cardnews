"""이슈 후보 수집: 언론사 RSS(기사 원문) + 구글 뉴스 주요 기사 제목(화제성 참고). 모두 무료·키 불필요."""
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


def collect_candidates(log=print):
    """(기사 후보, 화제 제목). 기사 후보는 원문 주소가 있는 기사로 제목 기준 중복을 걸러 최대 220건."""
    items = []
    for cat, url in config.RSS_FEEDS:
        try:
            got = fetch_rss(cat, url, 30)
            for g in got:
                g["source"] = g["source"] or urllib.parse.urlparse(g["link"]).netloc.replace("www.", "")
                if any(w in g["title"] for w in config.GOOD_NEWS_WORDS):
                    g["category"] = "미담"
            items += got
            log(f"  RSS {cat} {len(got)}건  {url[:60]}")
        except Exception as e:
            log(f"  RSS 실패 {url[:60]} ({e})")
    seen, uniq = set(), []
    for it in items:
        key = re.sub(r"[^0-9A-Za-z가-힣]", "", it["title"])[:18]
        if key and key not in seen and it["link"].startswith("http") and not re.search(r"\[(부고|인사|포토|게시판)\]", it["title"]):
            seen.add(key)
            uniq.append(it)
    trends = []
    for url in config.TREND_FEEDS:
        try:
            trends += [t["title"] for t in fetch_rss("", url, 20)]
        except Exception as e:
            log(f"  화제 피드 실패 {url[:50]} ({e})")
    return uniq[:220], list(dict.fromkeys(trends))[:60]


def related(issue_words, picked, pool, limit=6):
    """고른 기사 + 같은 이슈를 다룬 다른 언론사 기사(제목에 핵심 단어가 2개 이상 겹치는 것)."""
    out, links = list(picked), {p["link"] for p in picked}
    words = [w for w in issue_words if len(w) >= 2]
    scored = []
    for it in pool:
        if it["link"] in links:
            continue
        hit = sum(1 for w in words if w in it["title"])
        if hit >= 2:
            scored.append((hit, it))
    for _, it in sorted(scored, key=lambda x: -x[0]):
        out.append(it)
        if len(out) >= limit:
            break
    return out[:limit]


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
        alt = " ".join(s for s in re.split(r"(?<=다\.)\s+", clean(body)) if 30 < len(s) < 300)
        text = alt if len(alt) > len(text) else text
    return {"text": (clean(meta.get("og:description", "")) + " " + text)[:2500],
            "image": html.unescape(meta.get("og:image", "")), "site": clean(meta.get("og:site_name", ""))}
