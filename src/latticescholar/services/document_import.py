from __future__ import annotations

import html
import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, Iterable, List
from xml.etree import ElementTree as ET

from .pdf_parser import PDFParseError, PDFTextUnavailable, parse_pdf

MAX_ARCHIVE_UNCOMPRESSED = 40 * 1024 * 1024
MAX_ARCHIVE_MEMBER = 15 * 1024 * 1024
MAX_EXTRACTED_CHARS = 24_000

SUPPORTED_FORMATS = {
    ".pdf": "PDF",
    ".docx": "Word",
    ".pptx": "PowerPoint",
    ".xlsx": "Excel",
    ".odt": "OpenDocument",
    ".txt": "Text",
    ".md": "Markdown",
    ".rtf": "RTF",
    ".html": "HTML",
    ".htm": "HTML",
    ".csv": "CSV",
    ".json": "JSON",
    ".bib": "BibTeX",
    ".ris": "RIS",
    ".nbib": "NBIB",
    ".tex": "LaTeX",
    ".ipynb": "Jupyter Notebook",
}


class DocumentImportError(ValueError):
    """Raised when an Idea Lab document cannot be imported safely."""


@dataclass
class ImportedDocument:
    filename: str
    format: str
    text: str
    char_count: int
    truncated: bool = False
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class _ReadableHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self.hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: List[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "svg", "noscript"}:
            self.hidden_depth += 1
        elif tag in {"p", "div", "section", "article", "li", "br", "h1", "h2", "h3", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "svg", "noscript"} and self.hidden_depth:
            self.hidden_depth -= 1
        elif tag in {"p", "div", "section", "article", "li", "h1", "h2", "h3", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth:
            self.parts.append(data)


def _decode_text(content: bytes) -> str:
    for encoding in ("utf-8-sig", "gb18030", "utf-16", "utf-16-le", "utf-16-be"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _clean_text(value: str) -> str:
    value = html.unescape(value).replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[\t \u00a0]+", " ", line).strip() for line in value.splitlines()]
    cleaned: List[str] = []
    for line in lines:
        if line or (cleaned and cleaned[-1]):
            cleaned.append(line)
    return "\n".join(cleaned).strip()


def _safe_archive(content: bytes) -> zipfile.ZipFile:
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except (zipfile.BadZipFile, OSError) as exc:
        raise DocumentImportError("文件结构已损坏，无法解析") from exc
    total = 0
    for member in archive.infolist():
        total += member.file_size
        if member.flag_bits & 0x1:
            archive.close()
            raise DocumentImportError("暂不支持加密文档，请先在本地解除密码")
        if member.file_size > MAX_ARCHIVE_MEMBER or total > MAX_ARCHIVE_UNCOMPRESSED:
            archive.close()
            raise DocumentImportError("文档解压后过大，已为你停止解析")
    return archive


def _local_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _parse_xml(content: bytes, label: str) -> ET.Element:
    try:
        return ET.fromstring(content)
    except ET.ParseError as exc:
        raise DocumentImportError(f"{label} 中的 XML 结构已损坏") from exc


def _paragraphs(root: ET.Element, paragraph_names: Iterable[str], text_names: Iterable[str]) -> List[str]:
    paragraph_set = set(paragraph_names)
    text_set = set(text_names)
    result: List[str] = []
    for paragraph in root.iter():
        if _local_name(paragraph) not in paragraph_set:
            continue
        text = "".join(node.text or "" for node in paragraph.iter() if _local_name(node) in text_set)
        text = text.strip()
        if text:
            result.append(text)
    return result


def _read_member(archive: zipfile.ZipFile, name: str, label: str) -> bytes:
    try:
        return archive.read(name)
    except KeyError as exc:
        raise DocumentImportError(f"{label} 缺少必要内容，可能不是有效文档") from exc


def _extract_docx(content: bytes) -> tuple[str, Dict[str, Any]]:
    with _safe_archive(content) as archive:
        root = _parse_xml(_read_member(archive, "word/document.xml", "Word 文档"), "Word 文档")
        paragraphs = _paragraphs(root, {"p", "tr"}, {"t", "tab", "br"})
    return "\n".join(paragraphs), {"paragraphs": len(paragraphs)}


def _slide_number(name: str) -> int:
    match = re.search(r"slide(\d+)\.xml$", name)
    return int(match.group(1)) if match else 0


def _extract_pptx(content: bytes) -> tuple[str, Dict[str, Any]]:
    with _safe_archive(content) as archive:
        slide_names = sorted(
            (name for name in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)),
            key=_slide_number,
        )
        pages: List[str] = []
        for index, name in enumerate(slide_names, start=1):
            root = _parse_xml(archive.read(name), f"PowerPoint 第 {index} 页")
            lines = [node.text.strip() for node in root.iter() if _local_name(node) == "t" and node.text and node.text.strip()]
            if lines:
                pages.append(f"【第 {index} 页】\n" + "\n".join(lines))
    return "\n\n".join(pages), {"slides": len(slide_names)}


def _extract_xlsx(content: bytes) -> tuple[str, Dict[str, Any]]:
    with _safe_archive(content) as archive:
        shared: List[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = _parse_xml(archive.read("xl/sharedStrings.xml"), "Excel 共享文本")
            for item in root.iter():
                if _local_name(item) == "si":
                    shared.append("".join(node.text or "" for node in item.iter() if _local_name(node) == "t"))
        sheet_names = sorted(name for name in archive.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name))
        sheets: List[str] = []
        for index, name in enumerate(sheet_names, start=1):
            root = _parse_xml(archive.read(name), f"Excel 工作表 {index}")
            rows: List[str] = []
            for row in (node for node in root.iter() if _local_name(node) == "row"):
                values: List[str] = []
                for cell in (node for node in row if _local_name(node) == "c"):
                    cell_type = cell.attrib.get("t", "")
                    raw = next((node.text or "" for node in cell.iter() if _local_name(node) in {"v", "t"}), "")
                    if cell_type == "s" and raw.isdigit() and int(raw) < len(shared):
                        raw = shared[int(raw)]
                    values.append(raw.strip())
                if any(values):
                    rows.append(" | ".join(values))
            if rows:
                sheets.append(f"【工作表 {index}】\n" + "\n".join(rows))
    return "\n\n".join(sheets), {"sheets": len(sheet_names)}


def _extract_odt(content: bytes) -> tuple[str, Dict[str, Any]]:
    with _safe_archive(content) as archive:
        root = _parse_xml(_read_member(archive, "content.xml", "OpenDocument 文档"), "OpenDocument 文档")
        paragraphs = _paragraphs(root, {"p", "h"}, {"span", "a", "p", "h"})
    return "\n".join(paragraphs), {"paragraphs": len(paragraphs)}


def _extract_html(content: bytes) -> str:
    parser = _ReadableHTML()
    try:
        parser.feed(_decode_text(content))
    except Exception as exc:
        raise DocumentImportError("HTML 文件无法解析") from exc
    return "".join(parser.parts)


def _extract_rtf(content: bytes) -> str:
    value = _decode_text(content)

    def unicode_char(match: re.Match[str]) -> str:
        number = int(match.group(1))
        if number < 0:
            number += 65536
        return chr(number)

    value = re.sub(r"\\u(-?\d+)\??", unicode_char, value)
    value = re.sub(r"\\'(\w{2})", lambda match: bytes.fromhex(match.group(1)).decode("cp1252", "replace"), value)
    value = re.sub(r"\\(?:par|line)\b", "\n", value)
    value = re.sub(r"\\[a-zA-Z]+-?\d* ?", "", value)
    value = value.replace("\\{", "{").replace("\\}", "}").replace("\\\\", "\\")
    return value.replace("{", "").replace("}", "")


def _extract_ipynb(content: bytes) -> tuple[str, Dict[str, Any]]:
    try:
        payload = json.loads(_decode_text(content))
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise DocumentImportError("Jupyter Notebook 结构已损坏") from exc
    cells = payload.get("cells", []) if isinstance(payload, dict) else []
    sections: List[str] = []
    for index, cell in enumerate(cells, start=1):
        if not isinstance(cell, dict) or cell.get("cell_type") not in {"markdown", "code", "raw"}:
            continue
        source = cell.get("source", "")
        source = "".join(source) if isinstance(source, list) else str(source)
        if source.strip():
            label = {"markdown": "说明", "code": "代码", "raw": "原始文本"}[cell["cell_type"]]
            sections.append(f"【{label} Cell {index}】\n{source.strip()}")
    return "\n\n".join(sections), {"cells": len(cells)}


def extract_document(filename: str, content: bytes) -> ImportedDocument:
    safe_name = Path(filename or "document").name
    suffix = Path(safe_name).suffix.casefold()
    if suffix in {".doc", ".ppt", ".xls"}:
        target = {".doc": ".docx", ".ppt": ".pptx", ".xls": ".xlsx"}[suffix]
        raise DocumentImportError(f"这是旧版二进制 {suffix} 文件；请先在 Office/WPS 中另存为 {target}")
    if suffix not in SUPPORTED_FORMATS:
        supported = "、".join(sorted(SUPPORTED_FORMATS))
        raise DocumentImportError(f"暂不支持 {suffix or '无扩展名'} 文件；可上传：{supported}")
    if not content:
        raise DocumentImportError("文件为空，请重新选择")

    metadata: Dict[str, Any] = {}
    warnings: List[str] = []
    if suffix == ".pdf":
        try:
            parsed = parse_pdf(content, safe_name)
        except (PDFTextUnavailable, PDFParseError) as exc:
            raise DocumentImportError(str(exc)) from exc
        text = parsed.text
        metadata = {"pages": parsed.pages_parsed, "method": parsed.method}
        warnings.extend(parsed.warnings)
    elif suffix == ".docx":
        text, metadata = _extract_docx(content)
    elif suffix == ".pptx":
        text, metadata = _extract_pptx(content)
    elif suffix == ".xlsx":
        text, metadata = _extract_xlsx(content)
    elif suffix == ".odt":
        text, metadata = _extract_odt(content)
    elif suffix in {".html", ".htm"}:
        text = _extract_html(content)
    elif suffix == ".rtf":
        text = _extract_rtf(content)
    elif suffix == ".ipynb":
        text, metadata = _extract_ipynb(content)
    else:
        text = _decode_text(content)

    text = _clean_text(text)
    if len(text) < 12:
        raise DocumentImportError("未提取到足够的可读文字；扫描件请先进行 OCR")
    original_count = len(text)
    truncated = original_count > MAX_EXTRACTED_CHARS
    if truncated:
        text = text[:MAX_EXTRACTED_CHARS].rsplit("\n", 1)[0].strip() or text[:MAX_EXTRACTED_CHARS]
        warnings.append(f"为控制上下文长度，已保留前 {MAX_EXTRACTED_CHARS:,} 个字符")
    metadata["original_char_count"] = original_count
    return ImportedDocument(
        filename=safe_name,
        format=SUPPORTED_FORMATS[suffix],
        text=text,
        char_count=len(text),
        truncated=truncated,
        warnings=warnings,
        metadata=metadata,
    )
