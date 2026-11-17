"""사진 후보 수집·검증, 강조색 추출."""
import colorsys, io, urllib.parse
from PIL import Image
from . import collect


def load_image(url):
    """URL 에서 사진을 받아 PIL 이미지로. 너무 작거나 비율이 극단적이면 None."""
    try:
        raw, hdr = collect.http_get(url, {"Referer": "https://www.google.com/"}, timeout=12, limit=12_000_000)
        img = Image.open(io.BytesIO(raw))
        if getattr(img, "is_animated", False):
            return None
        img = img.convert("RGB")
    except Exception:
        return None
    w, h = img.size
    if w < 640 or h < 480 or not (0.45 <= w / h <= 2.4):
        return None
    return img


def candidates(articles_meta, queries, want=3, log=print):
    """[(PIL 이미지, 출처명)] 최대 want 개. 1순위: 기사 대표 이미지, 2순위: 네이버 이미지 검색."""
    urls, seen = [], set()
    for a in articles_meta:
        if a.get("image"):
            urls.append((a["image"], a.get("site") or a.get("source") or ""))
    for q in queries:
        try:
            for it in collect.naver("image", q, 8, "sim"):
                host = urllib.parse.urlparse(it.get("link", "")).netloc.replace("www.", "")
                urls.append((it.get("link", ""), host))
        except Exception as e:
            log(f"    이미지 검색 실패 '{q}' ({e})")
    out = []
    for url, credit in urls:
        key = url.split("?")[0]
        if not url.startswith("http") or key in seen:
            continue
        seen.add(key)
        img = load_image(url)
        if img is not None:
            out.append((img, credit or "온라인 커뮤니티"))
            if len(out) >= want:
                break
    return out


def accent_color(img):
    """사진에서 가장 눈에 띄는 유채색을 뽑아, 어두운 배경에서 잘 보이게 밝기·채도를 보정한다."""
    small = img.resize((64, 80)).quantize(8, method=Image.MEDIANCUT).convert("RGB")
    best, score = None, 0.0
    for count, (r, g, b) in small.getcolors(64 * 80):
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        sc = count * (s ** 1.5) * (0.3 + v)
        if s > 0.25 and v > 0.2 and sc > score:
            best, score = h, sc
    if best is None:                       # 무채색 사진이면 기본 노랑
        return (255, 214, 10)
    r, g, b = colorsys.hsv_to_rgb(best, 0.78, 1.0)
    # 파랑·보라 계열은 검정 위에서 어두워 보이므로 채도를 낮춰 밝게
    if 0.58 <= best <= 0.80:
        r, g, b = colorsys.hsv_to_rgb(best, 0.50, 1.0)
    return (int(r * 255), int(g * 255), int(b * 255))
