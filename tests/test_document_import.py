import io
import zipfile

import pytest

from latticescholar.services.document_import import (
    DocumentImportError,
    extract_document,
)
from tests.test_pdf_parser import make_research_pdf


def make_zip(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


def test_plain_text_html_rtf_and_metadata_formats():
    text = extract_document("前期工作.txt", "已完成数据收集与基线实验，并得到稳定结果。".encode())
    assert text.format == "Text"
    assert "基线实验" in text.text
    assert text.metadata["original_char_count"] == text.char_count

    gb = extract_document("数据.csv", "指标,数值\n准确率,0.91".encode("gb18030"))
    assert "准确率" in gb.text

    page = b"<html><style>bad</style><h1>Research</h1><p>Completed baseline experiment.</p><script>bad()</script></html>"
    html_result = extract_document("report.html", page)
    assert "Completed baseline" in html_result.text
    assert "bad()" not in html_result.text

    rtf = br"{\rtf1\ansi Existing work\par Result 91\% and \u20013?\u25968?\u25454?.}"
    rtf_result = extract_document("notes.rtf", rtf)
    assert "Existing work" in rtf_result.text
    assert "中数据" in rtf_result.text

    for suffix, label in ((".md", "Markdown"), (".json", "JSON"), (".bib", "BibTeX"), (".ris", "RIS"), (".nbib", "NBIB")):
        result = extract_document("record" + suffix, b"Title: sufficiently long research record")
        assert result.format == label

    tex = extract_document("paper.tex", b"\\section{Method} Reproducible experiment and verified result.")
    assert tex.format == "LaTeX"

    notebook = extract_document(
        "analysis.ipynb",
        b'{"cells":[{"cell_type":"markdown","source":["Research method and assumptions"]},{"cell_type":"code","source":"score = 0.91"}],"metadata":{}}',
    )
    assert notebook.metadata["cells"] == 2
    assert "score = 0.91" in notebook.text


def test_docx_pptx_xlsx_and_odt_extraction():
    docx = make_zip(
        {
            "word/document.xml": """<w:document xmlns:w="w"><w:body><w:p><w:r><w:t>已完成研究对象筛选</w:t></w:r></w:p><w:p><w:r><w:t>已验证轻量模型基线</w:t></w:r></w:p></w:body></w:document>"""
        }
    )
    result = extract_document("工作.docx", docx)
    assert result.format == "Word"
    assert result.metadata["paragraphs"] == 2
    assert "轻量模型基线" in result.text

    pptx = make_zip(
        {
            "ppt/slides/slide2.xml": '<p:sld xmlns:p="p" xmlns:a="a"><a:t>第二页结果与局限说明</a:t></p:sld>',
            "ppt/slides/slide1.xml": '<p:sld xmlns:p="p" xmlns:a="a"><a:t>第一页研究方法说明</a:t></p:sld>',
        }
    )
    slides = extract_document("slides.pptx", pptx)
    assert slides.metadata["slides"] == 2
    assert slides.text.index("第一页研究方法") < slides.text.index("第二页结果")

    xlsx = make_zip(
        {
            "xl/sharedStrings.xml": '<sst xmlns="x"><si><t>指标名称</t></si><si><t>准确率</t></si></sst>',
            "xl/worksheets/sheet1.xml": '<worksheet xmlns="x"><sheetData><row><c t="s"><v>0</v></c><c t="s"><v>1</v></c></row><row><c><v>0.91</v></c><c t="inlineStr"><is><t>已验证结果</t></is></c></row></sheetData></worksheet>',
        }
    )
    sheet = extract_document("metrics.xlsx", xlsx)
    assert sheet.metadata["sheets"] == 1
    assert "指标名称 | 准确率" in sheet.text
    assert "0.91 | 已验证结果" in sheet.text

    odt = make_zip(
        {
            "content.xml": '<office:document xmlns:office="o" xmlns:text="t"><text:h>已有工作</text:h><text:p>我们已完成公开数据的外部验证。</text:p></office:document>'
        }
    )
    open_doc = extract_document("work.odt", odt)
    assert open_doc.format == "OpenDocument"
    assert "外部验证" in open_doc.text


def test_pdf_extraction_truncation_and_failures():
    pdf = extract_document("paper.pdf", make_research_pdf())
    assert pdf.format == "PDF"
    assert pdf.metadata["pages"] == 3

    long_text = ("这是已完成的研究工作和可复现实验记录。\n" * 1800).encode()
    truncated = extract_document("long.md", long_text)
    assert truncated.truncated is True
    assert truncated.char_count <= 24_000
    assert truncated.warnings
    assert truncated.metadata["original_char_count"] > truncated.char_count

    with pytest.raises(DocumentImportError, match="暂不支持"):
        extract_document("program.exe", b"not an accepted research document")
    with pytest.raises(DocumentImportError, match="另存为 .docx"):
        extract_document("legacy.doc", b"old office binary")
    with pytest.raises(DocumentImportError, match="Notebook"):
        extract_document("broken.ipynb", b"not-json-at-all")
    with pytest.raises(DocumentImportError, match="文件为空"):
        extract_document("empty.txt", b"")
    with pytest.raises(DocumentImportError, match="足够"):
        extract_document("tiny.txt", b"tiny")
    with pytest.raises(DocumentImportError, match="损坏"):
        extract_document("broken.docx", b"not a zip archive")
    with pytest.raises(DocumentImportError, match="缺少"):
        extract_document("missing.docx", make_zip({"other.xml": "some sufficiently long text"}))
    with pytest.raises(DocumentImportError, match="XML"):
        extract_document("bad.docx", make_zip({"word/document.xml": "<broken>"}))


def test_archive_expansion_limit_is_rejected():
    oversized = make_zip({"word/document.xml": "x" * (15 * 1024 * 1024 + 1)})
    with pytest.raises(DocumentImportError, match="解压后过大"):
        extract_document("large.docx", oversized)
