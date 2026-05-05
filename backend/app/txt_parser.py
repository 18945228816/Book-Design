"""
TXT 电子书解析器

支持：
1. 提取书籍元信息（书名、作者）
2. 多层级章节结构（篇 → 章节）
3. 多种章节格式识别
"""

import re
from typing import List, Dict, Optional, Tuple


def normalize_heading_line(line: str) -> str:
    """
    规范化标题行：
    1. 去掉首尾空白
    2. 支持 <h2>五</h2> 这类 HTML 标题
    """
    # 去掉 BOM 字符后再 strip
    line = line.lstrip('﻿').strip()
    if not line:
        return ""

    html_heading = re.match(
        r'^<h[1-6][^>]*>\s*(.*?)\s*</h[1-6]>\s*$',
        line,
        re.IGNORECASE
    )
    if html_heading:
        return html_heading.group(1).strip()

    return line


def strip_redundant_leading_title(content: str, title: str) -> str:
    """
    如果正文开头重复了章节标题（纯文本或 <h*> 包裹），则去掉，避免前端出现标题重复。
    """
    if not content:
        return content

    lines = content.split('\n')
    while lines:
        first = normalize_heading_line(lines[0])
        if first == title:
            lines.pop(0)
            while lines and not lines[0].strip():
                lines.pop(0)
            continue
        break

    return '\n'.join(lines).strip()


def parse_book_info(content: str) -> Dict[str, str]:
    """
    从书籍开头提取元信息（书名、作者）

    常见格式：
    - 书名\n作者：xxx
    - 《书名》\n作者：xxx
    """
    info = {"title": "", "author": ""}

    # 取前500字符来提取信息
    header = content[:500]

    # 提取作者
    author_patterns = [
        r'作者[：:]\s*(.+)',
        r'著者[：:]\s*(.+)',
        r'作者[：:]?(.+)',
    ]

    for pattern in author_patterns:
        match = re.search(pattern, header)
        if match:
            author = match.group(1).strip()
            # 清理作者名（去掉多余内容）
            author = re.split(r'[\n,，、]', author)[0].strip()
            if len(author) <= 20:
                info["author"] = author
                break

    # 提取书名（第一行非空内容）
    lines = [line.strip() for line in content.split('\n') if line.strip()]
    if lines:
        first_line = lines[0]
        # 去掉可能的分隔符
        if not re.match(r'^[=]{3,}$|^[*]{3,}$|^[-]{3,}$', first_line):
            info["title"] = first_line[:100]

    return info


def parse_chapters(content: str, min_chapter_length: int = 50) -> List[dict]:
    """
    解析章节结构，支持多层级

    返回格式：
    [
        {
            "title": "序篇",
            "level": 1,  # 1=篇, 2=章节
            "content": "...",
            "children": [
                {"title": "一", "level": 2, "content": "..."},
                {"title": "二", "level": 2, "content": "..."},
            ]
        },
        ...
    ]

    为了兼容性，也会返回扁平化列表
    """
    content = content.strip()
    if not content:
        return [{"title": "全文", "level": 1, "content": "（空文件）", "children": []}]

    # 找到所有章节分割点
    split_points = find_chapter_splits(content)

    if not split_points:
        # 没有找到章节，作为单章处理
        return [{"title": "全文", "level": 1, "content": content, "children": []}]

    # 构建层级结构
    chapters = build_chapter_tree(content, split_points, min_chapter_length)

    return chapters


def clean_content_bom(content: str) -> str:
    """清理内容中的 BOM 字符和段落首行多余缩进"""
    if not content:
        return content
    lines = content.split('\n')
    result = []
    for line in lines:
        # 去掉每行开头的 BOM 和多余空格（保留内容本身）
        cleaned = line.lstrip('﻿').rstrip()
        result.append(cleaned)
    return '\n'.join(result).strip()


def extract_chapter_title(line: str) -> str:
    """从章节行中提取简洁标题"""
    # "正文 活着_一" → "一"
    m = re.match(r'^正文\s+\S+[_]\s*([一二三四五六七八九十百千万零\d]+)', line)
    if m:
        return m.group(1)
    return line


def find_chapter_splits(content: str) -> List[dict]:
    """
    找到所有章节分割点

    返回: [{"line_num": 10, "title": "序篇", "level": 1, "type": "main"}, ...]
    """

    lines = content.split('\n')
    splits = []

    # 预扫描：检测是否使用"正文 书名_X"格式
    has_zhengwen = any(re.match(r'^正文\s+\S+[_]', l.strip()) for l in lines[:50])

    # 大章节模式（篇级别）- level 1
    main_patterns = [
        # 序篇、引子、楔子
        r'^(序篇|序章|引子|楔子|前言|尾声|后记|附录)',
        # 第X篇
        r'^(第[一二三四五六七八九十百千万零\d]+篇)',
        # 第X卷
        r'^(第[一二三四五六七八九十百千万零\d]+卷)',
        # Part X
        r'^(Part\s+\d+)',
        # 正文 书名_X（如"正文 活着_一"）
        r'^正文\s+\S+[_]\s*([一二三四五六七八九十百千万零\d]+)',
    ]

    # 小章节模式（章级别）- level 2
    sub_patterns = [
        # 第X章
        r'^(第[一二三四五六七八九十百千万零\d]+章)',
        # 第X节
        r'^(第[一二三四五六七八九十百千万零\d]+节)',
        # 阿拉伯数字：1、2、3（单独一行）
        r'^(\d{1,3})$',
    ]
    # 仅在非"正文"格式时，把单独中文数字当作子章节
    if not has_zhengwen:
        sub_patterns.insert(0, r'^([一二三四五六七八九十百千万]+)$')

    # 合并主章节模式
    main_pattern = '|'.join(f'({p})' for p in main_patterns)
    sub_pattern = '|'.join(f'({p})' for p in sub_patterns)

    for i, raw_line in enumerate(lines):
        line = normalize_heading_line(raw_line)
        if not line:
            continue

        # 检查主章节
        if re.match(main_pattern, line, re.IGNORECASE):
            if len(line) <= 30:
                title = extract_chapter_title(line)
                splits.append({
                    "line_num": i,
                    "title": title,
                    "level": 1,
                    "type": "main"
                })
                continue

        # 检查子章节
        if re.match(sub_pattern, line, re.IGNORECASE):
            if len(line) <= 30:
                splits.append({
                    "line_num": i,
                    "title": line,
                    "level": 2,
                    "type": "sub"
                })

    return splits


def build_chapter_tree(content: str, splits: List[dict], min_length: int) -> List[dict]:
    """构建章节树结构"""

    lines = content.split('\n')

    # 找到第一个章节的位置（之前的内容作为简介）
    first_chapter_start = splits[0]["line_num"] if splits else len(lines)

    # 提取简介部分
    intro_content = '\n'.join(lines[:first_chapter_start]).strip()

    chapters = []

    # 添加简介（如果有）
    if intro_content and len(intro_content) >= min_length:
        chapters.append({
            "title": "简介",
            "level": 0,
            "content": intro_content,
            "children": []
        })

    # 处理章节
    main_chapters = []  # 收集主章节
    current_main = None

    for idx, split in enumerate(splits):
        # 计算当前章节的内容范围（跳过标题行）
        start = split["line_num"] + 1
        end = splits[idx + 1]["line_num"] if idx + 1 < len(splits) else len(lines)

        chapter_content = '\n'.join(lines[start:end]).strip()
        chapter_content = strip_redundant_leading_title(chapter_content, split["title"])
        chapter_content = clean_content_bom(chapter_content)

        if split["level"] == 1:
            # 主章节是“容器节点”，即使正文为空，也要保留层级关系
            chapter = {
                "title": split["title"],
                "level": split["level"],
                "content": chapter_content if len(chapter_content) >= min_length else "",
                "children": []
            }
            if current_main:
                main_chapters.append(current_main)
            current_main = chapter
            continue

        # 子章节正文太短时跳过
        if len(chapter_content) < min_length:
            continue

        chapter = {
            "title": split["title"],
            "level": split["level"],
            "content": chapter_content,
            "children": []
        }

        if current_main:
            current_main["children"].append(chapter)
        else:
            # 没有主章节，直接添加
            main_chapters.append(chapter)

    # 添加最后一个主章节
    if current_main:
        main_chapters.append(current_main)

    chapters.extend(main_chapters)

    return chapters


def flatten_chapters(chapters: List[dict]) -> List[dict]:
    """将树形结构扁平化为列表，用于数据库存储"""

    result = []

    for chapter in chapters:
        # 添加主章节
        flat = {
            "title": chapter["title"],
            "level": chapter["level"],
            "content": chapter["content"],
            "parent_title": None
        }
        result.append(flat)

        # 添加子章节
        for child in chapter.get("children", []):
            child_flat = {
                "title": child["title"],
                "level": child["level"],
                "content": child["content"],
                "parent_title": chapter["title"]
            }
            result.append(child_flat)

    return result


def detect_encoding(file_bytes: bytes) -> str:
    """检测文件编码"""

    encodings = ['utf-8', 'gbk', 'gb2312', 'gb18030', 'big5', 'utf-16']

    for encoding in encodings:
        try:
            file_bytes.decode(encoding)
            return encoding
        except (UnicodeDecodeError, LookupError):
            continue

    return 'utf-8'


def read_txt_file(file_bytes: bytes) -> str:
    """读取 TXT 文件内容，自动检测编码"""

    encoding = detect_encoding(file_bytes)
    return file_bytes.decode(encoding, errors='ignore')
