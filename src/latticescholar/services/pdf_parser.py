from __future__ import annotations

import os
import re
import shutil
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from importlib import import_module
from io import BytesIO
from typing import Any, Dict, List, Sequence, Tuple

import pdfplumber
from pypdf import PdfReader

pymupdf = None
pymupdf4llm = None


def _load_optional_pymupdf(require_llm: bool = False) -> bool:
    global pymupdf, pymupdf4llm
    try:
        if pymupdf is None:
            pymupdf = import_module("pymupdf")
        if require_llm and pymupdf4llm is None:
            pymupdf4llm = import_module("pymupdf4llm")
    except ImportError:
        return False
    return pymupdf is not None and (not require_llm or pymupdf4llm is not None)


class PDFParseError(RuntimeError):
    """The PDF container cannot be opened safely."""


class PDFTextUnavailable(PDFParseError):
    """The PDF opened, but no trustworthy text could be extracted."""


@dataclass
class PDFParseResult:
    text: str
    filename: str
    pages_total: int
    pages_parsed: int
    char_count: int
    method: str
    quality: str
    quality_score: float
    detected_language: str
    ocr_used: bool
    ocr_available: bool
    truncated: bool
    sections_found: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    title_candidate: str = ""


_SECTION_PATTERNS = {
    "摘要": r"^(abstract|摘要|摘\s*要)\b",
    "引言": r"^(\d+[.、\s]*)?(introduction|background|引言|绪论|研究背景)\b",
    "方法": r"^(\d+[.、\s]*)?(methodology|methods?|materials and methods|方法|材料与方法|研究设计)\b",
    "结果": r"^(\d+[.、\s]*)?(results?|findings|结果|实验结果)\b",
    "讨论": r"^(\d+[.、\s]*)?(discussion|讨论)\b",
    "结论": r"^(\d+[.、\s]*)?(conclusions?|结论|结语)\b",
    "局限": r"^(\d+[.、\s]*)?(limitations?|threats to validity|局限|不足)\b",
}


def _normalize_repeated_line(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).strip().casefold()
    value = re.sub(r"\d+", "#", value)
    return re.sub(r"\s+", " ", value)


def _clean_block(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return ""
    joined: List[str] = []
    for line in lines:
        if not joined:
            joined.append(line)
            continue
        previous = joined[-1]
        if re.search(r"[A-Za-z]-$", previous) and re.match(r"^[a-z]", line):
            joined[-1] = previous[:-1] + line
        elif (
            not re.search(r"[.!?。！？:：;；]$", previous)
            and (re.match(r"^[a-z,(]", line) or re.search(r"[\u4e00-\u9fff]$", previous))
        ):
            joined[-1] = previous + ("" if re.match(r"^[\u4e00-\u9fff]", line) else " ") + line
        else:
            joined.append(line)
    return "\n".join(joined)


def _ordered_blocks(blocks: Sequence[Tuple[Any, ...]], width: float) -> List[str]:
    records = []
    for block in blocks:
        if len(block) < 7 or int(block[6]) != 0:
            continue
        x0, y0, x1, y1 = (float(value) for value in block[:4])
        value = str(block[4])
        cleaned = _clean_block(value)
        if cleaned:
            records.append((x0, y0, x1, y1, cleaned))
    if not records:
        return []

    middle = width / 2
    left = [
        item for item in records
        if item[2] <= width * 0.58 and (item[0] + item[2]) / 2 < middle
    ]
    right = [
        item for item in records
        if item[0] >= width * 0.42 and (item[0] + item[2]) / 2 >= middle
    ]
    column_layout = len(left) >= 2 and len(right) >= 2
    if not column_layout:
        return [item[4] for item in sorted(records, key=lambda item: (item[1], item[0]))]

    column_ids = {id(item) for item in left + right}
    spanning = [item for item in records if id(item) not in column_ids]
    first_column_y = min(item[1] for item in left + right)
    last_column_y = max(item[3] for item in left + right)
    header = [item for item in spanning if item[3] <= first_column_y + 8]
    footer = [item for item in spanning if item[1] >= last_column_y - 8]
    middle_spanning = [item for item in spanning if item not in header and item not in footer]
    ordered = (
        sorted(header, key=lambda item: (item[1], item[0]))
        + sorted(left, key=lambda item: (item[1], item[0]))
        + sorted(right, key=lambda item: (item[1], item[0]))
        + sorted(middle_spanning, key=lambda item: (item[1], item[0]))
        + sorted(footer, key=lambda item: (item[1], item[0]))
    )
    return [item[4] for item in ordered]


def _remove_repeated_headers_and_footers(pages: List[List[str]]) -> List[List[str]]:
    if len(pages) < 3:
        return pages
    candidates: Counter[str] = Counter()
    for blocks in pages:
        boundary_lines: List[str] = []
        for value in blocks[:2] + blocks[-2:]:
            lines = value.splitlines()
            boundary_lines.extend(lines[:1] + lines[-1:])
        candidates.update({_normalize_repeated_line(line) for line in boundary_lines if line})
    threshold = max(3, int(len(pages) * 0.45))
    repeated = {line for line, count in candidates.items() if line and count >= threshold}
    if not repeated:
        return pages
    cleaned_pages = []
    for blocks in pages:
        page_blocks = []
        for block in blocks:
            lines = [
                line
                for line in block.splitlines()
                if _normalize_repeated_line(line) not in repeated
            ]
            value = "\n".join(lines).strip()
            if value:
                page_blocks.append(value)
        cleaned_pages.append(page_blocks)
    return cleaned_pages


def _detect_language(text: str) -> str:
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if cjk > max(40, latin * 0.35):
        return "中文" if latin < cjk * 0.25 else "中英混合"
    if latin > max(40, cjk * 2):
        return "英文"
    return "混合或未知"


def _find_sections(text: str) -> List[str]:
    found = []
    for line in text.splitlines():
        cleaned = line.strip().strip("#* ")
        if not cleaned or len(cleaned) > 100:
            continue
        for name, pattern in _SECTION_PATTERNS.items():
            if name not in found and re.search(pattern, cleaned, flags=re.I):
                found.append(name)
    return found


def _title_candidate(pages: List[List[str]], filename: str) -> str:
    if pages:
        for block in pages[0][:6]:
            line = block.splitlines()[0].strip().lstrip("#* ").strip()
            if 8 < len(line) < 220 and not re.match(r"^(doi|https?://|\d+[.、])", line, re.I):
                return line
    return re.sub(r"\.pdf$", "", filename, flags=re.I)


def _score_quality(pages: List[List[str]], pages_parsed: int, ocr_used: bool) -> Tuple[float, str]:
    page_texts = ["\n".join(page) for page in pages]
    covered = sum(bool(re.sub(r"\s", "", text)) for text in page_texts) / max(1, pages_parsed)
    chars = sum(len(re.sub(r"\s", "", text)) for text in page_texts)
    density = min(1.0, chars / max(1, pages_parsed * 900))
    replacement = sum(text.count("�") for text in page_texts) / max(1, chars)
    score = max(0.0, min(1.0, 0.58 * covered + 0.42 * density - min(0.35, replacement * 20)))
    if ocr_used:
        score = min(score, 0.84)
    label = "high" if score >= 0.78 else "medium" if score >= 0.48 else "low"
    return round(score, 2), label


def _parse_with_pymupdf(
    content: bytes, max_pages: int, max_chars: int, enable_ocr: bool
) -> Tuple[List[List[str]], int, bool, bool, bool, List[str]]:
    if not _load_optional_pymupdf():
        raise ImportError
    try:
        document = pymupdf.open(stream=content, filetype="pdf")
    except Exception as exc:
        raise PDFParseError("PDF 文件损坏、格式异常或无法打开。") from exc
    if document.needs_pass:
        document.close()
        raise PDFParseError("PDF 已加密，请先在本地解除密码保护后再上传。")

    pages_total = document.page_count
    pages_to_read = min(pages_total, max_pages)
    ocr_available = bool(shutil.which("tesseract"))
    ocr_used = False
    page_blocks: List[List[str]] = []
    warnings: List[str] = []
    running_chars = 0
    for page_index in range(pages_to_read):
        page = document.load_page(page_index)
        blocks = page.get_text("blocks", sort=True)
        values = _ordered_blocks(blocks, page.rect.width)
        visible_chars = len(re.sub(r"\s", "", "\n".join(values)))
        if visible_chars < 60 and enable_ocr and ocr_available:
            try:
                try:
                    textpage = page.get_textpage_ocr(
                        language="chi_sim+eng", dpi=180, full=True
                    )
                except Exception:
                    textpage = page.get_textpage_ocr(language="eng", dpi=180, full=True)
                values = _ordered_blocks(
                    page.get_text("blocks", textpage=textpage, sort=True), page.rect.width
                )
                ocr_used = True
            except Exception:
                warnings.append(f"第 {page_index + 1} 页疑似扫描页，但本机 OCR 执行失败。")
        elif visible_chars < 60 and page.get_images(full=True) and not ocr_available:
            warnings.append(
                f"第 {page_index + 1} 页疑似图片型页面，本机未安装 Tesseract，未执行 OCR。"
            )
        page_blocks.append(values)
        running_chars += sum(len(value) for value in values)
        if running_chars >= max_chars:
            break
    document.close()
    truncated = len(page_blocks) < pages_total or running_chars >= max_chars
    return page_blocks, pages_total, ocr_used, ocr_available, truncated, warnings


def _parse_with_pymupdf4llm(
    content: bytes, max_pages: int, max_chars: int
) -> Tuple[List[List[str]], int, bool]:
    """Extract a Markdown reading stream with multi-column and table awareness."""
    if not _load_optional_pymupdf(require_llm=True):
        raise ImportError
    try:
        document = pymupdf.open(stream=content, filetype="pdf")
    except Exception as exc:
        raise PDFParseError("PDF 文件损坏、格式异常或无法打开。") from exc
    if document.needs_pass:
        document.close()
        raise PDFParseError("PDF 已加密，请先在本地解除密码保护后再上传。")
    pages_total = document.page_count
    pages_to_read = min(pages_total, max_pages)
    try:
        chunks = pymupdf4llm.to_markdown(
            document,
            pages=list(range(pages_to_read)),
            page_chunks=True,
            show_progress=False,
            table_strategy="lines_strict",
        )
    except Exception:
        document.close()
        raise
    document.close()
    pages: List[List[str]] = []
    running_chars = 0
    for chunk in chunks:
        markdown = str(chunk.get("text") or "") if isinstance(chunk, dict) else str(chunk)
        blocks = [
            _clean_block(value)
            for value in re.split(r"\n\s*\n", markdown)
            if _clean_block(value)
        ]
        pages.append(blocks)
        running_chars += sum(len(value) for value in blocks)
        if running_chars >= max_chars:
            break
    return pages, pages_total, len(pages) < pages_total or running_chars >= max_chars


def _parse_with_pypdf(
    content: bytes, max_pages: int, max_chars: int
) -> Tuple[List[List[str]], int, bool]:
    try:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted:
            raise PDFParseError("PDF 已加密，请先在本地解除密码保护后再上传。")
        pages_total = len(reader.pages)
        pages: List[List[str]] = []
        running_chars = 0
        for page in reader.pages[:max_pages]:
            try:
                value = page.extract_text(
                    extraction_mode="layout", layout_mode_space_vertically=False
                )
            except Exception:
                value = page.extract_text() or ""
            cleaned = _clean_block(value or "")
            pages.append([cleaned] if cleaned else [])
            running_chars += len(cleaned)
            if running_chars >= max_chars:
                break
        return pages, pages_total, len(pages) < pages_total or running_chars >= max_chars
    except PDFParseError:
        raise
    except Exception as exc:
        raise PDFParseError("PDF 文件损坏、格式异常或无法打开。") from exc


def _parse_with_pdfplumber(
    content: bytes, max_pages: int, max_chars: int
) -> Tuple[List[List[str]], int, bool]:
    """Permissively licensed layout extraction with simple column-aware ordering."""
    try:
        document = pdfplumber.open(BytesIO(content))
    except Exception as exc:
        raise PDFParseError("PDF 文件损坏、格式异常或无法打开。") from exc
    try:
        pages_total = len(document.pages)
        pages: List[List[str]] = []
        running_chars = 0
        for page in document.pages[:max_pages]:
            words = page.extract_words(
                x_tolerance=2,
                y_tolerance=3,
                keep_blank_chars=False,
                use_text_flow=False,
            )
            rows: List[List[Dict[str, Any]]] = []
            for word in sorted(words, key=lambda item: (float(item["top"]), float(item["x0"]))):
                if rows and abs(float(word["top"]) - float(rows[-1][0]["top"])) <= 3:
                    rows[-1].append(word)
                else:
                    rows.append([word])
            blocks: List[Tuple[Any, ...]] = []
            for row in rows:
                chunks: List[List[Dict[str, Any]]] = [[]]
                for word in sorted(row, key=lambda item: float(item["x0"])):
                    if chunks[-1] and float(word["x0"]) - float(chunks[-1][-1]["x1"]) > page.width * 0.12:
                        chunks.append([])
                    chunks[-1].append(word)
                for chunk in chunks:
                    text = " ".join(str(word["text"]) for word in chunk).strip()
                    if text:
                        blocks.append(
                            (
                                min(float(word["x0"]) for word in chunk),
                                min(float(word["top"]) for word in chunk),
                                max(float(word["x1"]) for word in chunk),
                                max(float(word["bottom"]) for word in chunk),
                                text,
                                0,
                                0,
                            )
                        )
            values = _ordered_blocks(blocks, float(page.width))
            pages.append(values)
            running_chars += sum(len(value) for value in values)
            if running_chars >= max_chars:
                break
        return pages, pages_total, len(pages) < pages_total or running_chars >= max_chars
    finally:
        document.close()


def parse_pdf(
    content: bytes,
    filename: str = "",
    *,
    max_pages: int = 50,
    max_chars: int = 80000,
    enable_ocr: bool = True,
) -> PDFParseResult:
    """Extract a traceable reading stream while keeping the file entirely in memory."""
    warnings: List[str] = []
    engine = os.getenv("LATTICE_PDF_ENGINE", "core").strip().casefold()
    if engine != "pymupdf":
        try:
            pages, pages_total, truncated = _parse_with_pdfplumber(content, max_pages, max_chars)
            method = "pdfplumber_layout"
        except PDFParseError:
            pages, pages_total, truncated = _parse_with_pypdf(content, max_pages, max_chars)
            method = "pypdf_layout_fallback"
            warnings.append("PDFPlumber 版面解析失败，已使用 pypdf 兼容模式。")
        ocr_used = False
        ocr_available = False
    else:
        pages, pages_total, truncated, ocr_used, ocr_available, method, warnings = (
            _parse_with_optional_pymupdf(content, max_pages, max_chars, enable_ocr)
        )

    pages = _remove_repeated_headers_and_footers(pages)
    page_chunks = []
    for index, blocks in enumerate(pages):
        page_text = "\n\n".join(blocks).strip()
        if page_text:
            page_chunks.append(f"【第 {index + 1} 页】\n{page_text}")
    text = "\n\n".join(page_chunks)
    text = re.sub(r"(?<=[A-Za-z])-\s*\n\s*(?=[a-z])", "", text)
    text = re.sub(r"\n{4,}", "\n\n", text).strip()[:max_chars]
    if len(re.sub(r"\s", "", text)) < 20:
        if enable_ocr and engine == "pymupdf" and not ocr_available:
            raise PDFTextUnavailable(
                "该文件疑似扫描版或图片型 PDF，本机未检测到 Tesseract OCR。"
                "请安装 OCR 后重试，或上传可检索文字版 PDF。"
            )
        raise PDFTextUnavailable("未能提取到足够的可读文字，请检查 PDF 字体编码或扫描质量。")

    quality_score, quality = _score_quality(pages, len(pages), ocr_used)
    if quality == "low":
        warnings.append("本次文本提取质量偏低，请先核对原文证据，再使用分析结论。")
    if truncated:
        warnings.append(f"文档超过分析上限，仅处理前 {len(pages)} 页或 {max_chars} 字符。")
    if any(len(block) < 8 for page in pages for block in page):
        warnings.append("检测到较多短文本块，公式、表格或多栏区域可能需要回看原文。")
    return PDFParseResult(
        text=text,
        filename=filename,
        pages_total=pages_total,
        pages_parsed=len(pages),
        char_count=len(text),
        method=method,
        quality=quality,
        quality_score=quality_score,
        detected_language=_detect_language(text),
        ocr_used=ocr_used,
        ocr_available=ocr_available,
        truncated=truncated,
        sections_found=_find_sections(text),
        warnings=list(dict.fromkeys(warnings)),
        title_candidate=_title_candidate(pages, filename),
    )


def _parse_with_optional_pymupdf(
    content: bytes, max_pages: int, max_chars: int, enable_ocr: bool
) -> Tuple[List[List[str]], int, bool, bool, bool, str, List[str]]:
    """Run the explicitly selected AGPL/commercial optional PDF engine."""
    warnings: List[str] = []
    try:
        pages, pages_total, truncated = _parse_with_pymupdf4llm(
            content, max_pages, max_chars
        )
        native_chars = len(re.sub(r"\s", "", "".join("".join(page) for page in pages)))
        if native_chars < max(60, len(pages) * 20):
            raise PDFTextUnavailable("结构化文字层过少，需要尝试 OCR。")
        ocr_used = False
        ocr_available = bool(shutil.which("tesseract"))
        method = "pymupdf4llm_markdown"
    except PDFTextUnavailable:
        pages, pages_total, ocr_used, ocr_available, truncated, parser_warnings = (
            _parse_with_pymupdf(content, max_pages, max_chars, enable_ocr)
        )
        method = "pymupdf_blocks+ocr" if ocr_used else "pymupdf_blocks"
        warnings.append("结构化文字层不足，已自动切换到逐页 OCR 兼容流程。")
        warnings.extend(parser_warnings)
    except ImportError:
        try:
            pages, pages_total, ocr_used, ocr_available, truncated, parser_warnings = (
                _parse_with_pymupdf(content, max_pages, max_chars, enable_ocr)
            )
            method = "pymupdf_blocks+ocr" if ocr_used else "pymupdf_blocks"
            warnings.append("Markdown 版面解析组件不可用，已使用多栏文本块兼容模式。")
            warnings.extend(parser_warnings)
        except ImportError:  # pragma: no cover - PyMuPDF is a declared dependency
            pages, pages_total, truncated = _parse_with_pypdf(content, max_pages, max_chars)
            ocr_used = False
            ocr_available = False
            method = "pypdf_layout_fallback"
            warnings.append("高精度版面解析组件不可用，已使用兼容模式；多栏顺序可能不准确。")
    except PDFParseError:
        raise
    except Exception:
        pages, pages_total, ocr_used, ocr_available, truncated, parser_warnings = (
            _parse_with_pymupdf(content, max_pages, max_chars, enable_ocr)
        )
        method = "pymupdf_blocks+ocr" if ocr_used else "pymupdf_blocks"
        warnings.append("结构化版面解析失败，已自动切换到文本块兼容模式。")
        warnings.extend(parser_warnings)

    return pages, pages_total, truncated, ocr_used, ocr_available, method, warnings
