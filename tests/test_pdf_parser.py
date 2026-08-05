import re
from io import BytesIO

import pytest
from reportlab.pdfgen import canvas

from latticescholar.config import Settings
from latticescholar.models import AnalyzeRequest
from latticescholar.services.analyzer import AnalyzerService
from latticescholar.services.llm import LLMService
from latticescholar.services.pdf_parser import PDFParseError, parse_pdf


def make_research_pdf(page_count=3):
    output = BytesIO()
    document = canvas.Canvas(output, pagesize=(595, 842))
    for index in range(page_count):
        document.setFont("Helvetica", 9)
        document.drawString(48, 810, "Journal Header 2026")
        if index == 0:
            document.setFont("Helvetica-Bold", 17)
            document.drawString(48, 765, "A Reproducible Multimodal Research Framework")
            text = document.beginText(48, 730)
            text.setFont("Helvetica", 11)
            for line in ["Abstract", "Current clinical models lack external validation.", "We propose a novel multi-", "modal framework for diagnosis."]:
                text.textLine(line)
            document.drawText(text)
        elif index == 1:
            left = document.beginText(48, 765)
            right = document.beginText(320, 765)
            for item in (left, right):
                item.setFont("Helvetica", 11)
            for line in ["2 Methods", "We evaluate the method on", "two independent datasets.", "We compare three baselines."]:
                left.textLine(line)
            for line in ["3 Results", "Results show improved", "calibration and robustness.", "An ablation confirms it."]:
                right.textLine(line)
            document.drawText(left)
            document.drawText(right)
        else:
            text = document.beginText(48, 765)
            text.setFont("Helvetica", 11)
            for line in ["4 Discussion", "However, multi-center external validation remains future work.", "5 Conclusion", "The method improves calibration on the evaluated datasets."]:
                text.textLine(line)
            document.drawText(text)
        document.setFont("Helvetica", 9)
        document.drawString(280, 22, f"Page {index + 1}")
        document.showPage()
    document.save()
    return output.getvalue()


def test_pdf_parser_preserves_pages_cleans_layout_and_reports_quality():
    parsed = parse_pdf(make_research_pdf(), "demo-paper.pdf")
    assert parsed.pages_total == 3
    assert parsed.pages_parsed == 3
    assert parsed.method == "pdfplumber_layout"
    assert parsed.quality in {"medium", "high"}
    assert "【第 1 页】" in parsed.text and "【第 3 页】" in parsed.text
    assert "Journal Header" not in parsed.text
    assert re.search(r"multi[ -]?modal", parsed.text, flags=re.I)
    assert {"摘要", "方法", "结果", "讨论", "结论"}.issubset(parsed.sections_found)
    assert parsed.title_candidate.startswith("A Reproducible")


def test_pdf_parser_rejects_non_pdf_with_chinese_message():
    with pytest.raises(PDFParseError):
        parse_pdf(b"%PDF-1.4 invalid", "bad.pdf")


@pytest.mark.asyncio
async def test_english_paper_gets_chinese_explanation_and_four_question_readout():
    analyzer = AnalyzerService(LLMService(Settings(llm_provider="none")))
    result = await analyzer.analyze(
        AnalyzeRequest(
            title="A multimodal framework",
            abstract=(
                "Current clinical models lack external validation. "
                "We propose a novel multimodal framework. We evaluate it on two datasets "
                "and compare it with baseline models. Results show improved calibration. "
                "However, multi-center validation remains future work."
            ),
            use_llm=False,
        )
    )
    explanatory_text = " ".join(
        [result.core_problem, *result.methods, *result.innovations, *result.findings, *result.limitations]
    )
    assert len(re.findall(r"[\u4e00-\u9fff]", explanatory_text)) >= 30
    assert result.output_language == "zh-CN"
    assert len(result.key_questions) == 4
    assert all(question.points for question in result.key_questions)
    structured_text = " ".join(
        point.title + point.detail
        for question in result.key_questions
        for point in question.points
    )
    assert len(re.findall(r"[\u4e00-\u9fff]", structured_text)) >= 80
    assert "论文将以下" not in structured_text
    assert not re.search(r'“[^”]{40,}”', structured_text)
    assert result.key_questions[2].verdict in {"信息不足", "部分支持", "文本证据较完整 · 仍需核验"}
    assert "仍需核验：" in result.key_questions[2].answer
    assert "外部验证" in result.key_questions[2].answer.split("仍需核验：", 1)[1]
    assert any(point.title == "外部验证：信息不足" for point in result.key_questions[2].points)
    assert not any("lack external validation" in item.quote for item in result.evidence if item.claim == "方法证据")
    assert any(item.quote.startswith("We propose") for item in result.evidence)
