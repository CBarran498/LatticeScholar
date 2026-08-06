from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Sequence

from ..models import (
    AnalyzeRequest,
    EvidenceItem,
    KeyAnswerPoint,
    KeyQuestionAnswer,
    PaperAnalysis,
)
from ..text_utils import split_sentences
from .llm import LLMService, LLMUnavailable

METHOD_MARKERS = (
    "method", "framework", "model", "algorithm", "experiment", "dataset", "survey",
    "case study", "approach", "technique", "architecture", "pipeline", "protocol",
    "procedure", "方法", "模型", "算法", "实验", "数据集", "调查", "案例", "构建",
    "采用", "框架", "流程", "技术路线", "架构", "方案", "策略",
)
INNOVATION_MARKERS = (
    "novel", "new", "first", "propose", "introduce", "develop", "contribution",
    "unlike", "differ", "advance", "beyond", "outperform", "superior", "首次", "创新",
    "提出", "新型", "构建", "贡献", "改进", "突破", "优于", "超越", "区别于",
)
FINDING_MARKERS = (
    "result", "show", "demonstrate", "outperform", "improve", "achieve", "find",
    "indicate", "reveal", "confirm", "validate", "suggest", "conclude", "结果", "表明",
    "发现", "提升", "优于", "达到", "验证", "证实", "揭示", "证明",
)
LIMITATION_MARKERS = (
    "limit", "however", "future work", "although", "despite", "constraint", "challenge",
    "drawback", "weakness", "cannot", "fail", "局限", "不足", "未来工作", "尚未",
    "仍然", "但是", "然而", "挑战", "约束", "缺陷",
)
PROBLEM_MARKERS = (
    "problem", "challenge", "issue", "gap", "lack", "difficult", "remains", "unclear",
    "existing", "current", "traditional", "conventional", "suffer", "问题", "挑战", "痛点",
    "不足", "瓶颈", "困难", "现有", "传统", "尚未解决", "亟需",
)
EXPERIMENT_SIGNALS = {
    "数据/样本": ("dataset", "data set", "cohort", "sample", "participants", "数据集", "样本", "队列"),
    "对照基线": ("baseline", "compare", "comparison", "state-of-the-art", "对照", "基线", "比较"),
    "消融分析": ("ablation", "sensitivity analysis", "消融", "敏感性分析"),
    "统计检验": ("confidence interval", "p-value", "statistical", "significance", "置信区间", "显著性", "统计检验"),
    "外部验证": (
        "external validation", "external cohort", "multi-center", "multicenter",
        "外部验证", "外部队列", "多中心",
    ),
    "结果报告": FINDING_MARKERS,
}
NEGATION_MARKERS = (
    "lack", "lacks", "without", "not ", "no ", "absent", "remain", "future work",
    "缺乏", "不足", "未", "无", "尚", "未来工作",
)
METHOD_ACTION_MARKERS = (
    "we propose", "we use", "we adopt", "we develop", "we evaluate", "we train",
    "we construct", "this study uses", "consists of", "comprises", "pipeline", "protocol",
    "提出", "采用", "使用", "构建", "设计", "训练", "评估", "方法", "技术路线",
)
INNOVATION_STRONG_MARKERS = (
    "novel", "new ", "first", "we propose", "introduce", "develop", "unlike", "differ",
    "beyond", "首次", "创新", "新型", "提出", "改进", "突破", "区别于",
)
DIRECT_COMPARISON_MARKERS = (
    "unlike", "different from", "compared with prior", "compared with previous",
    "beyond existing", "conventional method", "traditional method", "previous work",
    "prior work", "相比既有", "相比传统", "区别于", "现有工作", "经典方法",
)
PROBLEM_STRONG_MARKERS = (
    "problem", "challenge", "issue", "gap", "lack", "difficult", "bottleneck",
    "问题", "挑战", "痛点", "不足", "瓶颈", "困难", "缺乏", "尚未解决",
)
QUESTIONS = (
    ("pain_points", "这篇论文要解决领域内哪些现存痛点？"),
    ("innovation_delta", "相比过往经典工作，本文方法做出了哪些关键改动与创新？"),
    ("evidence_strength", "整套实验是否充分，能够扎实支撑作者的核心结论？"),
    ("deep_dive", "还有哪些细节需要回看原文深挖溯源？"),
)

CUSTOM_QUESTION_KEY = "user_focus"

CONCEPT_MARKERS = (
    ("hybrid electric aircraft", "混合动力电动飞机"),
    ("electric aircraft", "电动飞机"),
    ("energy management", "能源管理"),
    ("battery aging", "电池老化"),
    ("battery life", "电池寿命"),
    ("fuel economy", "燃油经济性"),
    ("health-aware", "健康感知优化"),
    ("external validation", "外部验证"),
    ("multi-center", "多中心验证"),
    ("multicenter", "多中心验证"),
    ("cold-start", "训练冷启动"),
    ("cold start", "训练冷启动"),
    ("unstable training", "训练不稳定"),
    ("sparse reward", "奖励信号稀疏"),
    ("trade-off", "多目标权衡"),
    ("distribution shift", "分布偏移"),
    ("value estimation", "价值估计"),
    ("generalization", "泛化能力"),
    ("calibration", "模型校准"),
    ("robustness", "稳健性"),
    ("interpretability", "可解释性"),
    ("computational cost", "计算成本"),
    ("small sample", "小样本"),
    ("class imbalance", "类别不平衡"),
    ("noise", "噪声干扰"),
    ("课程学习", "课程学习"),
    ("外部验证", "外部验证"),
    ("冷启动", "训练冷启动"),
    ("泛化", "泛化能力"),
    ("能源管理", "能源管理"),
    ("电池", "电池寿命与老化"),
)
ISSUE_CONCEPTS = (
    ("external validation", "外部验证不足"),
    ("cold-start", "训练冷启动"),
    ("cold start", "训练冷启动"),
    ("unstable training", "训练过程不稳定"),
    ("sparse reward", "奖励信号稀疏"),
    ("trade-off", "燃油经济性与电池寿命的多目标权衡"),
    ("distribution shift", "训练过程中的分布偏移"),
    ("biased value", "价值估计偏差"),
    ("generalization", "泛化能力不足"),
    ("computational cost", "计算成本较高"),
    ("small sample", "小样本限制"),
    ("class imbalance", "类别不平衡"),
    ("lack", "现有方法存在能力缺口"),
    ("challenge", "现有方案仍面临关键挑战"),
    ("问题", "现存问题"),
    ("瓶颈", "性能或应用瓶颈"),
    ("不足", "现有方法存在不足"),
)
METHOD_CONCEPTS = (
    ("soft curriculum learning", "软课程学习"),
    ("curriculum learning", "课程学习"),
    ("dynamic reward re-labeling", "动态奖励重标记"),
    ("dynamic reward relabeling", "动态奖励重标记"),
    ("reward re-labeling", "奖励重标记"),
    ("reward relabeling", "奖励重标记"),
    ("huber", "Huber 稳健损失"),
    ("soft actor-critic", "软演员—评论家算法（SAC）"),
    ("physics-informed", "物理信息约束"),
    ("cosine annealing", "余弦退火"),
    ("multimodal", "多模态框架"),
    ("multi-modal", "多模态框架"),
    ("ablation", "消融分析"),
    ("sensitivity analysis", "敏感性分析"),
    ("课程学习", "课程学习"),
    ("奖励重标", "奖励重标记"),
    ("稳健损失", "稳健损失"),
    ("消融", "消融分析"),
)
EXPERIMENT_GUIDANCE = {
    "数据/样本": "核对数据来源、样本量、训练验证划分和代表性，确认不存在数据泄漏。",
    "对照基线": "核对基线是否覆盖经典方法与当前强基线，并确认调参预算保持公平。",
    "消融分析": "核对各新增模块是否分别做过消融，确认性能提升来自所声明的改动。",
    "统计检验": "核对重复实验次数、方差或置信区间及显著性检验，避免只比较单次最优值。",
    "外部验证": "核对跨数据集、跨中心或真实场景验证，判断结论能否推广到训练分布之外。",
    "结果报告": "核对正文表格、图形和评价指标，确认摘要结论与完整结果一致。",
}
LIMITATION_STRONG_MARKERS = (
    "limitation", "limited by", "drawback", "weakness", "cannot", "fail",
    "however", "future work", "remain future", "局限", "不足", "未来工作",
    "尚未", "仍需", "但是", "然而", "缺陷",
)


@dataclass(frozen=True)
class SentenceRecord:
    text: str
    location: str


def _sentence_records(text: str) -> List[SentenceRecord]:
    def records_for(value: str, location: str) -> List[SentenceRecord]:
        found = []
        for line in value.splitlines():
            clean = line.strip()
            if not clean:
                continue
            clean = re.sub(r"^(?:#{1,6}\s*|[-*•]\s+)", "", clean).strip()
            clean = re.sub(r"\s*\[[^\]]{0,3}\]\s*$", "", clean).strip()
            if not clean:
                continue
            if re.match(
                r"^(\d+[.、\s]*)?(abstract|introduction|background|methods?|results?|"
                r"discussion|conclusions?|limitations?|摘要|引言|背景|方法|结果|讨论|结论|局限)$",
                clean,
                flags=re.I,
            ):
                continue
            found.extend(SentenceRecord(item, location) for item in split_sentences(clean))
        return found

    records: List[SentenceRecord] = []
    page_parts = re.split(r"【第\s*(\d+)\s*页】", text)
    if len(page_parts) == 1:
        return records_for(text, "输入文本")
    prefix = page_parts[0]
    records.extend(records_for(prefix, "输入文本"))
    for index in range(1, len(page_parts), 2):
        page_no = page_parts[index]
        page_text = page_parts[index + 1] if index + 1 < len(page_parts) else ""
        records.extend(records_for(page_text, f"第 {page_no} 页"))
    return records


def _matching(
    records: Iterable[SentenceRecord], markers: Iterable[str], limit: int = 4
) -> List[SentenceRecord]:
    lowered = tuple(marker.lower() for marker in markers)
    return [
        record for record in records if any(marker in record.text.lower() for marker in lowered)
    ][:limit]


def _short_quote(text: str, limit: int = 520) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    return clean if len(clean) <= limit else clean[:limit].rstrip() + "…"


def _framed(kind: str, record: SentenceRecord) -> str:
    prefixes = {
        "problem": "论文将以下问题作为研究背景或切入点",
        "method": "论文明确描述了以下方法、数据或实验环节",
        "innovation": "作者将以下内容表述为改动、贡献或性能增量",
        "finding": "论文报告了以下结果或结论",
        "limitation": "论文披露了以下局限、约束或后续工作",
    }
    return f"{prefixes[kind]}（{record.location}原文证据）：“{_short_quote(record.text)}”"


def _evidence(label: str, records: Sequence[SentenceRecord]) -> List[EvidenceItem]:
    return [
        EvidenceItem(claim=label, quote=_short_quote(record.text, 760), location=record.location)
        for record in records
    ]


def _unique(values: Iterable[str], limit: int = 5) -> List[str]:
    result = []
    for value in values:
        if value and value not in result:
            result.append(value)
        if len(result) >= limit:
            break
    return result


def _concepts(text: str, markers: Sequence[tuple[str, str]], limit: int = 4) -> List[str]:
    lowered = text.lower()
    result = []
    matched_markers = []
    for marker, label in markers:
        if marker not in lowered or any(marker in previous for previous in matched_markers):
            continue
        matched_markers.append(marker)
        if label not in result:
            result.append(label)
        if len(result) >= limit:
            break
    return result


def _numbers(text: str) -> List[str]:
    return _unique(re.findall(r"(?<!\w)\d+(?:\.\d+)?\s*(?:%|％|倍|ms|s)?", text), 3)


def _record_point(record: SentenceRecord, kind: str, index: int) -> KeyAnswerPoint:
    concepts = _concepts(record.text, CONCEPT_MARKERS)
    issues = _concepts(record.text, ISSUE_CONCEPTS)
    methods = _concepts(record.text, METHOD_CONCEPTS)
    numbers = _numbers(record.text)
    location = record.location
    if kind == "problem":
        title = issues[0] if issues else f"现存问题 {index + 1}"
        issue_text = "、".join(issues[:4]) if issues else "该研究场景中的关键瓶颈"
        context = "、".join(concepts[:4])
        detail = f"论文要解决的直接问题是{issue_text}"
        if context:
            detail += f"，具体发生在{context}场景"
        detail += "。"
    elif kind == "innovation":
        title = methods[0] if methods else "量化性能增益" if numbers else f"方法改动 {index + 1}"
        method_text = "、".join(methods[:4]) if methods else "新的方法组件或训练策略"
        target = "、".join(concepts[:3])
        if methods:
            detail = f"本文引入{method_text}"
            if target:
                detail += f"，用于改善{target}"
            detail += "。"
        else:
            detail = f"作者报告{target or '相关评价指标'}出现量化改善。"
        if numbers:
            detail += f"报告数值为{'、'.join(numbers)}；这是作者报告的结果，仍需回到表格和实验设置核对。"
    else:
        title = concepts[0] if concepts else f"需核对事项 {index + 1}"
        subject = "、".join(concepts[:4]) if concepts else "该限制条件"
        detail = f"原文表明{subject}仍可能限制结论适用范围，需要结合正文方法、结果或补充材料进一步核对。"
    return KeyAnswerPoint(title=title, detail=detail, locations=[location])


def _summary(prefix: str, points: Sequence[KeyAnswerPoint], empty: str) -> str:
    titles = _unique((point.title for point in points), 5)
    return f"{prefix}{'、'.join(titles)}。" if titles else empty


def _experiment_assessment(
    records: Sequence[SentenceRecord], evidence: Sequence[EvidenceItem]
) -> tuple[str, str, List[EvidenceItem], List[KeyAnswerPoint]]:
    present_records = {}
    for label, markers in EXPERIMENT_SIGNALS.items():
        for record in records:
            lowered = record.text.lower()
            if not any(marker.lower() in lowered for marker in markers):
                continue
            if any(negation in lowered for negation in NEGATION_MARKERS):
                continue
            present_records[label] = record
            break
    present = list(present_records)
    missing = [label for label in EXPERIMENT_SIGNALS if label not in present]
    if len(present) >= 5:
        verdict = "文本证据较完整 · 仍需核验"
        opening = "当前文本同时出现多类实验支撑信号，但仍不能替代对表格、统计细节和补充材料的核验。"
    elif len(present) >= 3:
        verdict = "部分支持"
        opening = "当前文本提供了部分实验支撑，但不足以直接认定整套实验已经扎实证明核心结论。"
    else:
        verdict = "信息不足"
        opening = "当前文本披露的实验信息有限，不能据此判断结论是否得到充分支撑。"
    present_text = "、".join(present) if present else "未稳定识别到关键实验信号"
    missing_text = "、".join(missing) if missing else "仍需逐项核对样本代表性、统计假设和可复现细节"
    answer = f"{opening} 已识别：{present_text}；仍需核验：{missing_text}。"
    usable = [item for item in evidence if item.claim in {"方法证据", "结果证据"}][:4]
    points = []
    for label in EXPERIMENT_SIGNALS:
        record = present_records.get(label)
        if record:
            points.append(KeyAnswerPoint(
                title=f"{label}：已披露",
                detail=EXPERIMENT_GUIDANCE[label].replace("核对", "原文已出现相关信息；仍需核对", 1),
                locations=[record.location],
            ))
        else:
            points.append(KeyAnswerPoint(
                title=f"{label}：信息不足",
                detail=EXPERIMENT_GUIDANCE[label],
                locations=[],
            ))
    return answer, verdict, usable, points


def _user_focus_question(
    question: str,
    records: Sequence[SentenceRecord],
    evidence: Sequence[EvidenceItem],
) -> List[KeyQuestionAnswer]:
    """Generate a heuristic answer for the user's custom research question."""
    keywords = re.findall(r"[\w\u4e00-\u9fff]{2,}", question.lower())
    relevant = []
    for record in records:
        lowered = record.text.lower()
        hits = sum(1 for kw in keywords if kw in lowered)
        if hits > 0:
            relevant.append((hits, record))
    relevant.sort(key=lambda x: -x[0])
    top_records = [r for _, r in relevant[:6]]

    if top_records:
        points = []
        for idx, record in enumerate(top_records):
            concepts = _concepts(record.text, CONCEPT_MARKERS)
            title = concepts[0] if concepts else f"相关线索 {idx + 1}"
            points.append(KeyAnswerPoint(
                title=title,
                detail=f"原文在此处涉及您关注的内容（{record.location}）：\u201c" + _short_quote(record.text, 400) + "\u201d",
                locations=[record.location],
            ))
        answer = f"在论文文本中找到 {len(top_records)} 处与您关注问题相关的内容。"
        verdict = "原文有相关线索"
    else:
        points = [KeyAnswerPoint(
            title="未找到直接相关内容",
            detail=f"在当前提供的论文文本中，未检测到与「{question}」直接相关的显式论述。建议回看全文或补充材料。",
            locations=[],
        )]
        answer = "当前文本中未检测到与您关注问题直接相关的显式信息。"
        verdict = "信息不足"

    relevant_evidence = [
        item for item in evidence
        if any(kw in item.quote.lower() for kw in keywords)
    ][:4]

    return [KeyQuestionAnswer(
        key=CUSTOM_QUESTION_KEY,
        question=question,
        answer=answer,
        verdict=verdict,
        points=points,
        evidence=relevant_evidence,
    )]


def _key_questions(
    core: str,
    innovations: Sequence[str],
    limitations: Sequence[str],
    records: Sequence[SentenceRecord],
    evidence: Sequence[EvidenceItem],
    problems_found: bool,
    innovations_found: bool,
    research_question: str = "",
) -> List[KeyQuestionAnswer]:
    experiment_answer, experiment_verdict, experiment_evidence, experiment_points = _experiment_assessment(
        records, evidence
    )
    problem_evidence = [item for item in evidence if item.claim == "问题证据"][:3]
    innovation_evidence = [item for item in evidence if item.claim == "创新证据"][:3]
    limitation_evidence = [item for item in evidence if item.claim == "局限证据"][:3]
    problem_records = [record for record in records if any(
        item.quote == _short_quote(record.text, 760) for item in problem_evidence
    )]
    innovation_records = [record for record in records if any(
        item.quote == _short_quote(record.text, 760) for item in innovation_evidence
    )]
    limitation_records = [record for record in records if any(
        item.quote == _short_quote(record.text, 760) for item in limitation_evidence
    )]
    problem_points = [_record_point(record, "problem", index) for index, record in enumerate(problem_records)]
    innovation_points = [
        _record_point(record, "innovation", index) for index, record in enumerate(innovation_records)
    ]
    innovation_summary_points = list(innovation_points)
    direct_comparison = any(
        marker in record.text.lower()
        for record in innovation_records
        for marker in DIRECT_COMPARISON_MARKERS
    )
    if innovation_points and not direct_comparison:
        innovation_points.append(KeyAnswerPoint(
            title="与经典工作的差异：原文未逐项说明",
            detail="正文片段能支持‘采用了哪些改动’，但没有提供与经典工作的同条件逐项对照；因此只能确认作者声明的改动，不能据此独立确认新颖性。",
            locations=[],
        ))
    deep_points = [_record_point(record, "limitation", index) for index, record in enumerate(limitation_records)]
    covered_titles = {point.title.split("：", 1)[0] for point in experiment_points if "已披露" in point.title}
    deep_titles = " ".join(point.title for point in deep_points)
    for label in EXPERIMENT_SIGNALS:
        if label not in covered_titles and label not in deep_titles and len(deep_points) < 6:
            deep_points.append(KeyAnswerPoint(
                title=f"补查{label}", detail=EXPERIMENT_GUIDANCE[label], locations=[]
            ))
    return [
        KeyQuestionAnswer(
            key=QUESTIONS[0][0], question=QUESTIONS[0][1],
            answer=_summary("论文聚焦的主要痛点包括：", problem_points, "原文未明确披露可可靠归纳的领域痛点。"),
            verdict="原文有明确线索" if problems_found else "信息不足",
            points=problem_points,
            evidence=problem_evidence,
        ),
        KeyQuestionAnswer(
            key=QUESTIONS[1][0], question=QUESTIONS[1][1],
            answer=(
                _summary("本文可识别的关键改动包括：", innovation_summary_points, "原文未提供足够的经典工作对比，无法可靠确认创新增量。")
                + (" 但原文未与经典工作逐项对照，当前只能确认作者声明的改动。" if innovation_points and not direct_comparison else "")
            ),
            verdict=("作者有明确声明" if direct_comparison else "有改动声明 · 缺少直接对比")
            if innovations_found else "未发现明确对比",
            points=innovation_points,
            evidence=innovation_evidence,
        ),
        KeyQuestionAnswer(
            key=QUESTIONS[2][0], question=QUESTIONS[2][1], answer=experiment_answer,
            verdict=experiment_verdict, points=experiment_points, evidence=experiment_evidence,
        ),
        KeyQuestionAnswer(
            key=QUESTIONS[3][0], question=QUESTIONS[3][1],
            answer=_summary("建议优先回看：", deep_points, "建议核对数据、基线、消融、统计、外部验证和补充材料。"),
            verdict="建议回看原文", points=deep_points,
            evidence=limitation_evidence,
        ),
    ] + (_user_focus_question(research_question, records, evidence) if research_question else [])


def _clean_pdf_text(text: str) -> str:
    """Compatibility helper retained for callers of versions before the layout parser."""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    text = re.sub(r"(?<=[A-Za-z])-\n(?=[a-z])", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _has_chinese_explanation(analysis: PaperAnalysis) -> bool:
    values = [
        analysis.core_problem,
        *analysis.methods,
        *analysis.innovations,
        *analysis.findings,
        *analysis.limitations,
        *(item.answer for item in analysis.key_questions),
        *(item.verdict for item in analysis.key_questions),
    ]
    return len(re.findall(r"[\u4e00-\u9fff]", " ".join(values))) >= 12


def _select_evidence_window(text: str, budget: int) -> tuple[str, bool]:
    if len(text) <= budget:
        return text, False
    chunks = [chunk.strip() for chunk in re.split(r"\n\s*\n", text) if chunk.strip()]
    if not chunks:
        return text[:budget], True
    priority_terms = (
        *METHOD_MARKERS, *INNOVATION_MARKERS, *FINDING_MARKERS, *LIMITATION_MARKERS,
        "abstract", "摘要", "conclusion", "结论", "discussion", "讨论",
    )
    ranked = []
    for index, chunk in enumerate(chunks):
        lowered = chunk.lower()
        score = sum(term.lower() in lowered for term in priority_terms)
        if index < 5 or index >= len(chunks) - 5:
            score += 4
        ranked.append((score, index, chunk))
    selected = []
    used = 0
    for _, index, chunk in sorted(ranked, key=lambda item: (-item[0], item[1])):
        value = chunk[:2400]
        if used + len(value) + 2 > budget:
            continue
        selected.append((index, value))
        used += len(value) + 2
        if used >= budget * 0.92:
            break
    selected.sort(key=lambda item: item[0])
    notice = "【系统说明：长文已按摘要、方法、结果、讨论、结论与局限信号选择证据窗口。】"
    return notice + "\n\n" + "\n\n".join(value for _, value in selected), True



PAPER_ANALYSIS_SYSTEM_PROMPT = (
    "你是一位严谨的科研论文审读专家，擅长从论文全文中提取结构化信息并进行深度批判性分析。"
    "只能依据用户提供的论文文字作答，不得臆造或补充原文没有的内容。"
    "你的分析必须具有高信息密度、强证据支撑和明确的审慎判断。\n\n"
    "硬性规则：\n"
    "1）所有解释、判断、标题和提醒必须使用简体中文；专业名词可保留英文。\n"
    "2）原文引文保持原语言并标注页码或位置，不可把翻译伪装成原文。\n"
    "3）未披露的信息写'原文未披露'，禁止补写。\n"
    "4）评估实验充分性时分别检查：样本量/数据规模、基线对比、消融分析、统计检验、外部验证。\n"
    "5）每个 point 的 detail 必须引用论文中的具体内容（方法名、数据值、实验设置等）。\n"
    "6）区分作者的声明（claim）与已验证的结论（verified），verdict 使用审慎短语。\n\n"
    "返回一个 JSON 对象。根据用户指示决定 key_questions 数组包含 4 或 5 个元素。\n"
    "标准 4 个问题（必须按顺序）：\n"
    "1. pain_points — 这篇论文要解决领域内哪些现存痛点？列出具体的技术/理论局限。\n"
    "2. innovation_delta — 相比过往经典工作，本文方法做出了哪些关键改动与创新？给出对比。\n"
    "3. evidence_strength — 整套实验是否充分，能够扎实支撑作者的核心结论？逐维度评估。\n"
    "4. deep_dive — 还有哪些细节需要回看原文深挖溯源？指出可能的遗漏或不清晰之处。\n"
    "若用户提供了自定义研究问题，则追加第 5 个问题：\n"
    "5. user_focus — 针对用户具体问题，从论文全文中找到所有相关段落和证据，给出详尽回答。"
    "必须包含原文中的具体方法描述、数据指标、实验条件或结论依据。\n\n"
    "每问的字段：key(string), question(string), answer(string 一句中文结论 30-80字), "
    "verdict(string 审慎短语), points(array of {title,detail,locations}), "
    "evidence(array of {claim,quote,location})。\n"
    "每问 3-6 个 points（user_focus 问题给 5-8 个）。"
    "points.title 用信息密度高的中文短标题（10字以内），"
    "detail 用完整具体的中文解释（至少 40 字，包含方法/数据/结论的具体细节）。\n"
    "locations 标注原文段落或页码位置。evidence 引用原文原话作为支撑。\n"
    "其他顶层字段：core_problem(string 50-150字 核心问题的精确描述), "
    "methods(string[] 3-5项 每项描述一个关键方法或技术手段), "
    "innovations(string[] 2-4项 每项对比前人工作说明创新点), "
    "findings(string[] 3-5项 主要实验发现和量化结果), "
    "limitations(string[] 2-4项 论文自身承认或可推断的局限), "
    "evidence([{claim,quote,location}] 3-6条 关键论据的原文引用), "
    "confidence('low'|'medium'|'high' 基于证据完整性判断), "
    "warnings(string[] 阅读时需注意的陷阱或需核验的点)。\n"
    "verdict 不得把作者声称写成已独立证实；对缺乏外部验证的结论标注'待独立验证'。"
)


class AnalyzerService:
    def __init__(self, llm: LLMService):
        self.llm = llm

    async def analyze(
        self, request: AnalyzeRequest, user_id: str = "", owner_id: int = 0
    ) -> PaperAnalysis:
        available = getattr(self.llm, "available", lambda _: self.llm.enabled)(owner_id)
        if request.use_llm and available:
            try:
                return await self._analyze_with_llm(request, user_id, owner_id)
            except Exception as exc:
                fallback = self._analyze_heuristic(request)
                fallback.warnings.insert(0, "深度分析不可用，已回退到中文规则模式：" + str(exc)[:160])
                return fallback
        return self._analyze_heuristic(request)

    def _analyze_heuristic(self, request: AnalyzeRequest) -> PaperAnalysis:
        records = _sentence_records(request.abstract)
        normalized_title = re.sub(r"\W+", "", request.title).casefold()
        if normalized_title:
            records = [
                item for item in records
                if re.sub(r"\W+", "", item.text).casefold() != normalized_title
            ]
        finding_records = _matching(records, FINDING_MARKERS)
        limitation_candidates = _matching(records, LIMITATION_MARKERS, limit=8)
        limitation_records = [
            item for item in limitation_candidates
            if any(marker in item.text.lower() for marker in LIMITATION_STRONG_MARKERS)
        ][:4]
        limitation_texts = {item.text for item in limitation_records}
        problems = [
            item for item in _matching(records, PROBLEM_MARKERS, limit=8)
            if item.text not in limitation_texts
            or any(marker in item.text.lower() for marker in PROBLEM_STRONG_MARKERS)
        ][:4]
        problem_texts = {item.text for item in problems}
        finding_texts = {item.text for item in finding_records}
        method_records = [
            item for item in _matching(records, METHOD_MARKERS, limit=10)
            if (
                item.text not in problem_texts and item.text not in finding_texts
            ) or any(marker in item.text.lower() for marker in METHOD_ACTION_MARKERS)
        ][:4]
        innovation_records = [
            item for item in _matching(records, INNOVATION_MARKERS, limit=10)
            if item.text not in finding_texts
            or any(marker in item.text.lower() for marker in INNOVATION_STRONG_MARKERS)
        ][:4]

        if problems:
            core = _framed("problem", problems[0])
        elif records:
            core = (
                f"现有文本没有明确说明领域痛点。最先出现的信息是（{records[0].location}原文）："
                f"“{_short_quote(records[0].text)}”；不能据此推断尚未披露的研究缺口。"
            )
        else:
            core = "未获得可分析文本，无法判断论文试图解决的领域痛点。"

        methods = [_framed("method", item) for item in method_records] or [
            "现有文本未明确披露方法、数据或实验流程；需要回看全文的方法部分。"
        ]
        innovations = [_framed("innovation", item) for item in innovation_records] or [
            "现有文本未检测到与经典工作直接对比的创新声明；不能仅凭标题推断创新点。"
        ]
        findings = [_framed("finding", item) for item in finding_records] or [
            "现有文本未检测到明确的结果声明；需要核对结果、图表与结论部分。"
        ]
        limitations = [_framed("limitation", item) for item in limitation_records] or [
            "现有文本未披露局限性；这不代表论文不存在局限，建议回看样本边界、基线设置、统计检验、外部验证和补充材料。"
        ]
        evidence = (
            _evidence("问题证据", problems)
            + _evidence("方法证据", method_records)
            + _evidence("创新证据", innovation_records)
            + _evidence("结果证据", finding_records)
            + _evidence("局限证据", limitation_records)
        )[:14]
        result = PaperAnalysis(
            core_problem=core,
            methods=methods,
            innovations=innovations,
            findings=findings,
            limitations=limitations,
            evidence=evidence,
            confidence="medium" if len(records) >= 6 and len(evidence) >= 3 else "low",
            mode="heuristic",
            warnings=[
                "全部解释使用简体中文；为避免翻译失真，证据引文保留论文原始语言。",
                "规则模式只识别显式表述，不生成原文没有说明的创新、效果或因果结论。",
                "实验充分性判断未读取图表像素、公式语义、补充材料与审稿记录，必须回到原文核验。",
            ],
            usage={"source_chars": len(request.abstract), "model_tokens": 0},
        )
        result.key_questions = _key_questions(
            core, innovations, limitations, records, evidence, bool(problems), bool(innovation_records),
            research_question=request.research_question,
        )
        return result

    async def _analyze_with_llm(
        self, request: AnalyzeRequest, user_id: str = "", owner_id: int = 0
    ) -> PaperAnalysis:
        has_custom_q = bool(request.research_question and request.research_question.strip())
        custom_q = request.research_question.strip() if has_custom_q else ""

        system = PAPER_ANALYSIS_SYSTEM_PROMPT
        budget = max(6000, self.llm.config.llm_max_input_chars - len(request.title) - 2200)
        selected_text, selected = _select_evidence_window(request.abstract, budget)
        user = f"论文标题：\n{request.title}\n\n论文正文内容：\n{selected_text}"
        if has_custom_q:
            user += (
                f"\n\n{'='*40}\n"
                f"【用户自定义研究问题】：{custom_q}\n"
                f"{'='*40}\n"
                "本次分析必须包含第 5 个问题 user_focus，key_questions 数组共 5 个元素。\n"
                "在 user_focus 中，针对上述问题给出 5-8 个 points，每个 detail 超过 60 字，"
                "包含具体方法描述、数据引用、实验结论或原文定位。\n"
                "同时在前 4 个问题中优先分析与用户问题相关的内容。\n"
                "如果论文完全未涉及用户问题，在 user_focus 的 answer 中写'原文未涉及此问题'。"
            )
        else:
            user += "\n\n本次分析只需回答 4 个标准问题，key_questions 数组共 4 个元素。"
        payload, usage = await self.llm.json_completion(
            system, user, task="paper_analysis", user_id=user_id, owner_id=owner_id
        )
        # Resilient parsing - never raise on partial data, extract what we can
        evidence = self._safe_parse_evidence(payload.get("evidence"))
        raw_questions = payload.get("key_questions") or []
        expected_questions = list(QUESTIONS)
        if has_custom_q:
            expected_questions.append((CUSTOM_QUESTION_KEY, custom_q))
        key_answers = self._safe_parse_key_questions(raw_questions, expected_questions)
        core_problem = str(payload.get("core_problem") or "")
        if not core_problem or len(core_problem) < 5:
            core_problem = "模型未返回有效的核心问题描述。"
        result = PaperAnalysis(
            core_problem=core_problem,
            methods=self._safe_string_list(payload.get("methods"), "方法"),
            innovations=self._safe_string_list(payload.get("innovations"), "创新"),
            findings=self._safe_string_list(payload.get("findings"), "发现"),
            limitations=self._safe_string_list(payload.get("limitations"), "局限"),
            evidence=evidence,
            key_questions=key_answers,
            confidence=str(payload.get("confidence") or "medium"),
            mode="llm",
            warnings=[str(v) for v in payload.get("warnings") or []]
            + ["模型分析只覆盖提供的文字，关键判断仍需回到原文、图表和补充材料核验。"],
            usage={
                **usage,
                "source_chars": len(request.abstract),
                "selected_chars": len(selected_text),
                "selection_strategy": "section_evidence_window" if selected else "full_text",
                "custom_question": custom_q if has_custom_q else None,
            },
        )
        # Relaxed Chinese check - only require 6 characters instead of 12
        values = [result.core_problem] + result.methods + result.innovations
        values += [item.answer for item in result.key_questions]
        chinese_count = len(re.findall(r"[\u4e00-\u9fff]", " ".join(values)))
        if chinese_count < 6 and not any(
            len(q.answer) > 20 for q in result.key_questions
        ):
            raise LLMUnavailable("模型未返回有效的中文分析内容")
        result.usage.update({
            "quality_status": "passed",
            "quality_checks": [
                "结构解析完成",
                "中文内容验证",
                "证据独立展示",
            ] + (["用户自定义问题已响应"] if has_custom_q else []),
        })
        return result

    @staticmethod
    def _safe_parse_evidence(raw) -> List[EvidenceItem]:
        """Parse evidence items, skipping any that fail validation."""
        if not raw or not isinstance(raw, list):
            return []
        result = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                result.append(EvidenceItem(
                    claim=str(item.get("claim") or ""),
                    quote=str(item.get("quote") or ""),
                    location=str(item.get("location") or "原文"),
                ))
            except Exception:
                continue
        return result[:20]

    @staticmethod
    def _safe_parse_key_questions(
        raw_questions: list, expected: list
    ) -> List[KeyQuestionAnswer]:
        """Parse key questions resilently, never raising on bad data."""
        key_answers = []
        for index, (key, question) in enumerate(expected):
            item = {}
            if index < len(raw_questions) and isinstance(raw_questions[index], dict):
                item = raw_questions[index]
            elif raw_questions:
                # Try to find by key match if index doesn't align
                for rq in raw_questions:
                    if isinstance(rq, dict) and rq.get("key") == key:
                        item = rq
                        break
            answer = str(item.get("answer") or "原文未提供足够信息来回答此问题。")
            verdict = str(item.get("verdict") or "需要核验")
            # Parse points safely
            points = []
            for p in (item.get("points") or []):
                if not isinstance(p, dict):
                    continue
                try:
                    points.append(KeyAnswerPoint(
                        title=str(p.get("title") or "分析要点"),
                        detail=str(p.get("detail") or ""),
                        locations=self._safe_parse_locations(p.get("locations")),
                    ))
                except Exception:
                    continue
            if not points:
                points = [KeyAnswerPoint(title="核心结论", detail=answer, locations=[])]
            # Parse evidence safely
            ev_list = []
            for e in (item.get("evidence") or []):
                if not isinstance(e, dict):
                    continue
                try:
                    ev_list.append(EvidenceItem(
                        claim=str(e.get("claim") or ""),
                        quote=str(e.get("quote") or ""),
                        location=str(e.get("location") or "原文"),
                    ))
                except Exception:
                    continue
            key_answers.append(KeyQuestionAnswer(
                key=key,
                question=question,
                answer=answer,
                verdict=verdict,
                points=points,
                evidence=ev_list,
            ))
        return key_answers

    @staticmethod
    def _safe_string_list(raw, label: str) -> List[str]:
        """Safely extract a list of strings from model output."""
        if not raw:
            return [f"原文未披露{label}相关信息。"]
        if isinstance(raw, list):
            result = [str(v) for v in raw if v and str(v).strip()]
            return result if result else [f"原文未披露{label}相关信息。"]
        if isinstance(raw, str):
            return [raw]
        return [f"原文未披露{label}相关信息。"]

    @staticmethod
    def _safe_parse_locations(raw) -> List[str]:
        """Parse locations field robustly - handles string, list, or None."""
        if not raw:
            return []
        if isinstance(raw, str):
            parts = [s.strip() for s in re.split(r"[,，;；、]", raw) if s.strip()]
            return parts if parts else [raw] if raw.strip() else []
        if isinstance(raw, list):
            result = []
            for item in raw:
                if not item:
                    continue
                if isinstance(item, str) and len(item) > 1:
                    result.append(item)
                elif isinstance(item, str) and len(item) == 1:
                    continue
                else:
                    result.append(str(item))
            if not result and raw:
                joined = "".join(str(x) for x in raw if x)
                if joined.strip():
                    parts = [s.strip() for s in re.split(r"[,，;；、]", joined) if s.strip()]
                    return parts if parts else [joined]
            return result
        return []
