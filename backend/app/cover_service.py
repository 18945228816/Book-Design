"""
书籍封面获取：三级链路
1. 微信读书搜索真实出版封面（免费、快）
2. AI 图片模型生成装饰封面（付费、慢）
3. Pillow 本地排版封面（免费、离线兜底，保证每本书都有封面）

图片统一存到 UPLOAD_DIR/covers 下，返回可访问的相对 URL 路径。
"""

import asyncio
import hashlib
import os
import re
from typing import Optional, Tuple

import httpx

from .config import settings
from .logger import get_logger

logger = get_logger(__name__)

_WEREAD_SEARCH = "https://weread.qq.com/web/search/global"
_DOUBAN_SUGGEST = "https://book.douban.com/j/subject_suggest"
_COVER_DIR = os.path.join(settings.UPLOAD_DIR, "covers")
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")
_HTTP_HEADERS = {"User-Agent": _UA, "Referer": "https://weread.qq.com/"}
_DOUBAN_HEADERS = {"User-Agent": _UA, "Referer": "https://book.douban.com/"}


def _cover_path(book_id: str, ext: str) -> str:
    os.makedirs(_COVER_DIR, exist_ok=True)
    return os.path.join(_COVER_DIR, f"{book_id}.{ext}")


def _relative_url(abs_path: str) -> str:
    """backend/uploads/covers/x.jpg -> /uploads/covers/x.jpg"""
    norm = abs_path.replace("\\", "/")
    idx = norm.find("uploads/")
    return "/" + norm[idx:] if idx >= 0 else norm


# ---------- 1. 真实封面（豆瓣高清优先，微信读书兜底）----------

async def _fetch_douban_cover(client: httpx.AsyncClient, title: str, author: Optional[str]) -> Optional[bytes]:
    """豆瓣 suggest 接口拿高清封面（约 400x569），需带 Referer 否则 418。"""
    try:
        resp = await client.get(
            _DOUBAN_SUGGEST,
            params={"q": title},
            headers={"User-Agent": _UA},
            timeout=10,
        )
        resp.raise_for_status()
        items = resp.json()
    except Exception as exc:
        logger.warning(f"豆瓣搜索失败({title}): {exc}")
        return None

    if not isinstance(items, list) or not items:
        return None

    # 只取图书（type=b），按标题/作者匹配打分
    scored = []
    for it in items:
        if it.get("type") != "b":
            continue
        score = _score_match(title, it.get("title", ""), author or "", it.get("author_name", ""))
        if score > 0:
            scored.append((score, it.get("pic", "")))
    if not scored:
        return None

    scored.sort(key=lambda x: x[0], reverse=True)
    for _, pic in scored[:3]:
        if not pic:
            continue
        # suggest 返回的是小图(s)，换成大图(l)
        large = pic.replace("/view/subject/s/", "/view/subject/l/")
        for url in (large, pic):
            try:
                img = await client.get(url, headers=_DOUBAN_HEADERS, timeout=10)
                img.raise_for_status()
                if img.status_code == 200 and len(img.content) >= 3000 and \
                        img.headers.get("content-type", "").startswith("image"):
                    logger.info(f"豆瓣命中高清封面: {title} ({len(img.content)}B)")
                    return img.content
            except Exception:
                continue
    return None


def _score_match(title: str, candidate: str, author: str, cand_author: str) -> int:
    """标题越吻合分越高；作者也吻合额外加分。"""
    t = re.sub(r"\s+", "", title or "").lower()
    c = re.sub(r"\s+", "", candidate or "").lower()
    if not t or not c:
        return 0
    score = 0
    if t == c:
        score += 100
    elif t in c or c in t:
        score += 60
    else:
        # 去书名号/副标题后再比一次
        t2 = t.strip("《》").split(":")[0].split("：")[0]
        c2 = c.strip("《》").split(":")[0].split("：")[0]
        if t2 and (t2 in c2 or c2 in t2):
            score += 40
    if author and cand_author:
        a = re.sub(r"\s+", "", author).lower()
        ca = re.sub(r"\s+", "", cand_author).lower()
        if a and (a in ca or ca in a or any(p and p in ca for p in a.split(","))):
            score += 30
    return score


async def _fetch_weread_cover(client: httpx.AsyncClient, title: str, author: Optional[str]) -> Optional[bytes]:
    """微信读书封面（分辨率较低，作兜底）。搜索返回 s_ 小图，尽量换 b_ 大图。"""
    keyword = f"{title} {author}".strip() if author else title
    try:
        resp = await client.get(
            _WEREAD_SEARCH,
            params={"keyword": keyword},
            headers=_HTTP_HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning(f"微信读书搜索失败({title}): {exc}")
        return None

    candidates = []
    groups = data.get("books") or []
    # 兼容两种结构：books[].bookInfo 与 books[].bookInfos[].bookInfo
    for group in groups:
        items = group.get("bookInfos") or ([group] if group.get("bookInfo") else [])
        for item in items:
            bi = item.get("bookInfo") or item
            cover = bi.get("cover")
            if not cover:
                continue
            score = _score_match(title, bi.get("title", ""), author or "", bi.get("author", ""))
            if score > 0:
                candidates.append((score, cover))

    if not candidates:
        logger.info(f"微信读书未找到匹配封面: {title}")
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    for _, cover_url in candidates[:3]:
        # s_ 是 70px 小图；同一对象尝试 b_(140px) / m_(84px)
        bigger_urls = [
            re.sub(r"/s_(?=[^/]+\.jpg)", "/b_", cover_url),
            re.sub(r"/s_(?=[^/]+\.jpg)", "/m_", cover_url),
            cover_url,
        ]
        for url in bigger_urls:
            try:
                img = await client.get(url, headers=_HTTP_HEADERS, timeout=10)
                img.raise_for_status()
                if img.status_code == 200 and len(img.content) >= 1000 and \
                        img.headers.get("content-type", "").startswith("image"):
                    logger.info(f"微信读书命中封面: {title} ({len(img.content)}B)")
                    return img.content
            except Exception:
                continue
    return None


async def fetch_real_cover(
    client: httpx.AsyncClient, title: str, author: Optional[str]
) -> Optional[bytes]:
    """真实封面：豆瓣高清优先，搜不到再回退微信读书。"""
    cover = await _fetch_douban_cover(client, title, author)
    if cover:
        return cover
    return await _fetch_weread_cover(client, title, author)


# ---------- 2. AI 生成封面 ----------

async def fetch_ai_cover(title: str, author: Optional[str]) -> Optional[bytes]:
    # 延迟导入，避免无图片需求时也加载
    from .ai_service import generate_cover_image
    return await generate_cover_image(title, author)


# ---------- 3. Pillow 本地排版封面 ----------

# 几组典雅封面配色（上深下浅渐变感，直接取首尾两色）
_PALETTES = [
    ((44, 62, 82), (100, 124, 148)),
    ((92, 44, 56), (160, 96, 110)),
    ((38, 70, 83), (80, 140, 120)),
    ((82, 60, 96), (140, 110, 160)),
    ((112, 70, 42), (180, 130, 80)),
    ((30, 60, 90), (70, 120, 160)),
]


def generate_local_cover(title: str, author: Optional[str]) -> bytes:
    """用书名+作者生成竖版排版封面，返回 JPEG 字节。"""
    from PIL import Image, ImageDraw, ImageFont

    W, H = 600, 840
    seed = int(hashlib.md5((title or "").encode("utf-8")).hexdigest()[:8], 16)
    top, bottom = _PALETTES[seed % len(_PALETTES)]

    img = Image.new("RGB", (W, H), top)
    draw = ImageDraw.Draw(img)
    # 竖向渐变
    for y in range(H):
        ratio = y / H
        color = tuple(int(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3))
        draw.line([(0, y), (W, y)], fill=color)

    fonts_dir = "C:/Windows/Fonts"
    title_font_path = os.path.join(fonts_dir, "msyhbd.ttc")
    body_font_path = os.path.join(fonts_dir, "msyh.ttc")

    def load_font(path, size):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            return ImageFont.load_default()

    def wrap_text(text, font, max_width):
        text = (text or "").strip() or "未命名"
        lines, cur = [], ""
        for ch in text:
            trial = cur + ch
            if draw.textlength(trial, font=font) <= max_width:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = ch
        if cur:
            lines.append(cur)
        return lines[:4]

    # 装饰边框
    draw.rectangle([28, 28, W - 28, H - 28], outline=(255, 255, 255, 180), width=2)

    title_font = load_font(title_font_path, 52)
    lines = wrap_text(title, title_font, W - 120)
    line_h = 72
    total_h = line_h * len(lines)
    y = (H - total_h) // 2 - 40
    for line in lines:
        w = draw.textlength(line, font=title_font)
        draw.text(((W - w) / 2, y), line, font=title_font, fill=(255, 255, 255))
        y += line_h

    if author:
        author_font = load_font(body_font_path, 30)
        at = f"—— {author}"
        aw = draw.textlength(at, font=author_font)
        draw.text(((W - aw) / 2, y + 30), at, font=author_font, fill=(235, 235, 235))

    from io import BytesIO
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


# ---------- 编排：真封面 -> AI -> 本地 ----------

VALID_METHODS = ("real", "ai", "local")
_METHOD_EXT = {"real": "jpg", "ai": "png", "local": "jpg"}


def _preview_path(book_id: str, method: str, ext: str) -> str:
    os.makedirs(_COVER_DIR, exist_ok=True)
    return os.path.join(_COVER_DIR, f"{book_id}.preview.{method}.{ext}")


def _write_cover(book_id: str, ext: str, data: bytes) -> str:
    import glob
    target = _cover_path(book_id, ext)
    # 清掉同书的旧正式封面/预览（扩展名可能不同）
    for old in glob.glob(os.path.join(_COVER_DIR, f"{book_id}*")):
        if os.path.abspath(old) != os.path.abspath(target):
            try:
                os.remove(old)
            except OSError:
                pass
    with open(target, "wb") as f:
        f.write(data)
    return _relative_url(target)


async def _generate_by_method(method: str, title: str, author: Optional[str]) -> Optional[bytes]:
    if method == "real":
        async with httpx.AsyncClient(trust_env=False, follow_redirects=True) as client:
            return await fetch_real_cover(client, title, author)
    if method == "ai":
        return await fetch_ai_cover(title, author)
    if method == "local":
        return await asyncio.to_thread(generate_local_cover, title, author)
    return None


async def create_cover_preview(
    book_id: str, title: str, author: Optional[str], method: str
) -> Tuple[Optional[str], str]:
    """用指定方式生成封面，存为预览文件（不影响当前封面）。

    返回 (预览URL, method)；该方式拿不到（如搜不到真封面、AI 不可用）时返回 (None, method)。
    """
    if method not in VALID_METHODS:
        return None, method
    try:
        data = await _generate_by_method(method, title, author)
        if not data:
            return None, method
        ext = _sniff_ext(data, _METHOD_EXT[method])
        path = _preview_path(book_id, method, ext)
        with open(path, "wb") as f:
            f.write(data)
        # 清掉同方式旧扩展名的预览
        import glob
        for old in glob.glob(os.path.join(_COVER_DIR, f"{book_id}.preview.{method}.*")):
            if os.path.abspath(old) != os.path.abspath(path):
                try:
                    os.remove(old)
                except OSError:
                    pass
        logger.info(f"封面预览已生成({method}): book={book_id}")
        return _relative_url(path), method
    except Exception as exc:
        logger.warning(f"封面预览失败(book={book_id}, method={method}): {exc}")
        return None, method


def _sniff_ext(data: bytes, default: str) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return default


def promote_cover_preview(book_id: str, method: str) -> Optional[str]:
    """把某个已生成的预览封面提升为该书的正式封面，返回相对 URL。"""
    if method not in VALID_METHODS:
        return None

    import glob
    # 实际扩展名以落盘文件为准（AI 预览经本地叠字后是 jpg）
    matches = glob.glob(os.path.join(_COVER_DIR, f"{book_id}.preview.{method}.*"))
    if not matches:
        return None
    preview = matches[0]
    ext = os.path.basename(preview).rsplit(".", 1)[-1]

    # 清掉旧的正式封面（扩展名可能不同）和其它预览
    for old in glob.glob(os.path.join(_COVER_DIR, f"{book_id}*")):
        if os.path.abspath(old) != os.path.abspath(preview):
            try:
                os.remove(old)
            except OSError:
                pass

    canonical = _cover_path(book_id, ext)
    os.replace(preview, canonical)
    url = _relative_url(canonical)
    logger.info(f"封面已采用({method}): book={book_id} -> {url}")
    return url


async def acquire_cover(
    book_id: str, title: str, author: Optional[str], use_ai: bool = True
) -> Tuple[Optional[str], Optional[str]]:
    """按 真封面→AI→本地 的顺序获取封面，返回 (相对URL, 来源)；异常不抛出。

    来源取值：real / ai / local。
    """
    try:
        async with httpx.AsyncClient(trust_env=False, follow_redirects=True) as client:
            real = await fetch_real_cover(client, title, author)
            if real:
                return _write_cover(book_id, "jpg", real), "real"

        if use_ai:
            ai = await fetch_ai_cover(title, author)
            if ai:
                return _write_cover(book_id, _sniff_ext(ai, "png"), ai), "ai"

        local = await asyncio.to_thread(generate_local_cover, title, author)
        return _write_cover(book_id, "jpg", local), "local"
    except Exception as exc:
        logger.warning(f"获取封面失败(book={book_id}, title={title}): {exc}")
        try:
            local = await asyncio.to_thread(generate_local_cover, title, author)
            return _write_cover(book_id, "jpg", local), "local"
        except Exception:
            return None, None
