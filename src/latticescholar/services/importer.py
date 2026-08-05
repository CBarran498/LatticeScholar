from __future__ import annotations

import re
from typing import Dict, List, Optional

from ..models import Paper
from ..text_utils import clean_markup, stable_id


class BibliographyImportError(ValueError):
    pass


def _year(value: str):
    match = re.search(r"\b(19|20)\d{2}\b", value or "")
    return int(match.group(0)) if match else None


def _paper(fields: Dict[str, List[str]], source: str) -> Optional[Paper]:
    def first(*names: str) -> str:
        for name in names:
            values = fields.get(name, [])
            if values and values[0].strip():
                return values[0].strip()
        return ""

    title = first("TI", "T1", "ST", "TITLE")
    if not title:
        return None
    doi = first("DO", "DOI").replace("https://doi.org/", "").lower()
    url = first("UR", "URL") or ("https://doi.org/" + doi if doi else "")
    issn = [value for value in fields.get("SN", []) if value]
    return Paper(
        id=stable_id("import", doi or title),
        title=clean_markup(title),
        abstract=clean_markup(first("AB", "N2", "ABSTRACT")),
        authors=fields.get("AU", []) or fields.get("FAU", []) or fields.get("AUTHOR", []),
        year=_year(first("PY", "Y1", "DA", "DP", "YEAR")),
        venue=first("JO", "JF", "T2", "JA", "JT", "JOURNAL", "BOOKTITLE"),
        issn=issn,
        doi=doi,
        url=url,
        sources=[source],
        topics=fields.get("KW", [])[:8],
    )


def _parse_tagged(text: str, source: str) -> List[Paper]:
    records: List[Paper] = []
    fields: Dict[str, List[str]] = {}
    active = ""
    for raw in text.splitlines() + ["ER  -"]:
        match = re.match(r"^([A-Z0-9]{2,6})\s{0,2}-\s?(.*)$", raw)
        if match:
            tag, value = match.groups()
            if tag == "ER":
                paper = _paper(fields, source)
                if paper:
                    records.append(paper)
                fields, active = {}, ""
                continue
            active = tag
            fields.setdefault(tag, []).append(value.strip())
        elif active and raw.strip():
            fields[active][-1] += " " + raw.strip()
    return records


def _split_bib_entries(text: str) -> List[str]:
    entries = []
    start = 0
    while True:
        match = re.search(r"@[A-Za-z]+\s*\{", text[start:])
        if not match:
            break
        begin = start + match.start()
        brace = start + match.end() - 1
        depth = 0
        end = brace
        for index in range(brace, len(text)):
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        entries.append(text[begin:end])
        start = end
    return entries


def _parse_bibtex(text: str, source: str) -> List[Paper]:
    papers = []
    for entry in _split_bib_entries(text):
        fields: Dict[str, List[str]] = {}
        body = entry[entry.find(",") + 1 : -1]
        pattern = re.compile(
            r"(?is)([A-Za-z][\w-]*)\s*=\s*(?:\{((?:[^{}]|\{[^{}]*\})*)\}|\"([^\"]*)\")\s*,?"
        )
        for match in pattern.finditer(body):
            name = match.group(1).upper()
            value = (match.group(2) if match.group(2) is not None else match.group(3)) or ""
            value = re.sub(r"[{}]", "", value).strip()
            if name == "AUTHOR":
                fields[name] = [part.strip() for part in re.split(r"\s+and\s+", value) if part.strip()]
            else:
                fields.setdefault(name, []).append(value)
        paper = _paper(fields, source)
        if paper:
            papers.append(paper)
    return papers


def import_bibliography(filename: str, content: bytes, source: str = "Imported record") -> List[Paper]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = content.decode("gb18030")
        except UnicodeDecodeError as exc:
            raise BibliographyImportError("题录文件必须使用 UTF-8 或 GB18030 编码") from exc
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    papers = _parse_bibtex(text, source) if suffix == "bib" or "@article{" in text.lower() else _parse_tagged(text, source)
    if not papers:
        raise BibliographyImportError("未识别到题录；请从原平台导出 BibTeX、RIS、EndNote 或 NBIB 格式")
    return papers[:500]
