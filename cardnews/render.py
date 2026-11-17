"""카드뉴스 썸네일 렌더러 (1080x1350, 4:5).
사진 전체 채움 + 하단 검정 그라데이션 + 좌측 정렬 초굵은 헤드라인(첫 줄 강조색) + 브랜드 라벨."""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from . import config

W, H = 1080, 1350
MX = 84            # 좌우 여백
BOTTOM = 150       # 헤드라인 아래 여백


def cover(img, focus_y=0.3):
    r = max(W / img.width, H / img.height)
    img = img.resize((max(W, round(img.width * r)), max(H, round(img.height * r))), Image.LANCZOS)
    x = (img.width - W) // 2
    y = int((img.height - H) * focus_y)
    return img.crop((x, y, x + W, y + H))


def bottom_gradient(img, start=0.42, max_alpha=245):
    col = Image.new("L", (1, H), 0)
    for y in range(H):
        t = max(0.0, min(1.0, (y / H - start) / (1 - start)))
        col.putpixel((0, y), int(max_alpha * (t ** 1.25)))
    return Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), img, col.resize((W, H)))


def fit_font(lines, size=92, floor=56):
    while size > floor:
        f = ImageFont.truetype(config.FONT_HEAD, size)
        if max(f.getlength(l) for l in lines) <= W - MX * 2:
            return f
        size -= 2
    return ImageFont.truetype(config.FONT_HEAD, floor)


def fallback_bg(accent):
    """쓸 수 있는 사진이 없을 때의 단색 그라데이션 배경."""
    img = Image.new("RGB", (W, H), (14, 14, 18))
    glow = Image.new("RGB", (W, H), accent)
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).ellipse((W * 0.15, -H * 0.1, W * 1.2, H * 0.6), fill=110)
    return Image.composite(glow, img, mask.filter(ImageFilter.GaussianBlur(180)))


def render(bg, lines, out_path, accent=(255, 214, 10), brand=None):
    brand = brand or config.BRAND
    img = bottom_gradient(cover(bg.convert("RGB")))
    font = fit_font(lines)
    lh = int(font.size * 1.24)
    base = H - BOTTOM - lh * len(lines)
    # 헤드라인 그림자
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sh)
    for i, l in enumerate(lines):
        sd.text((MX, base + i * lh + 4), l, font=font, fill=(0, 0, 0, 170))
    sh = sh.filter(ImageFilter.GaussianBlur(10))
    img.paste(sh, (0, 0), sh)
    d = ImageDraw.Draw(img)
    # 브랜드 라벨
    fb = ImageFont.truetype(config.FONT_SUB, 30)
    d.rounded_rectangle((MX, base - 62, MX + 14, base - 34), 3, fill=accent)
    d.text((MX + 26, base - 66), brand, font=fb, fill=(255, 255, 255))
    for i, l in enumerate(lines):
        d.text((MX, base + i * lh), l, font=font, fill=accent if i == 0 else (255, 255, 255))
    img.save(out_path, "JPEG", quality=88, optimize=True)
    return out_path
