from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


class Paper(BaseModel):
    id: str
    title: str
    abstract: str = ""
    authors: List[str] = Field(default_factory=list)
    year: Optional[int] = None
    venue: str = ""
    issn: List[str] = Field(default_factory=list)
    doi: str = ""
    url: str = ""
    citation_count: Optional[int] = None
    open_access: Optional[bool] = None
    sources: List[str] = Field(default_factory=list)
    topics: List[str] = Field(default_factory=list)
    language: str = Field(default="unknown", pattern="^(zh|en|mixed|unknown)$")
    score: float = 0.0


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    english_query: str = Field(default="", max_length=500)
    limit: int = Field(default=20, ge=1, le=50)
    sources: List[str] = Field(
        default_factory=lambda: ["crossref", "semantic_scholar", "arxiv"]
    )
    year_from: Optional[int] = Field(default=None, ge=1900, le=2100)
    year_to: Optional[int] = Field(default=None, ge=1900, le=2100)
    language: str = Field(default="any", pattern="^(any|zh|en)$")
    has_abstract: Optional[bool] = None
    open_access_only: bool = False
    min_citations: int = Field(default=0, ge=0, le=1_000_000)
    sort_by: str = Field(default="relevance", pattern="^(relevance|newest|citations|completeness)$")
    project_id: Optional[int] = Field(default=None, ge=1)

    @field_validator("sources")
    @classmethod
    def valid_sources(cls, value: List[str]) -> List[str]:
        allowed = {
            "crossref",
            "semantic_scholar",
            "openalex",
            "arxiv",
            "pubmed",
            "web_of_science",
        }
        cleaned = list(dict.fromkeys(s.lower() for s in value if s.lower() in allowed))
        if not cleaned:
            raise ValueError("At least one supported source is required")
        return cleaned

    @model_validator(mode="after")
    def valid_year_range(self) -> SearchRequest:
        if self.year_from and self.year_to and self.year_from > self.year_to:
            raise ValueError("year_from cannot be later than year_to")
        return self


class SearchResponse(BaseModel):
    papers: List[Paper]
    source_status: Dict[str, str]
    cache_hit: bool = False
    elapsed_ms: int
    facets: Dict[str, int] = Field(default_factory=dict)
    notices: List[str] = Field(default_factory=list)
    quality: Dict[str, Any] = Field(default_factory=dict)


class SearchStrategyRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    field: str = Field(default="", max_length=200)
    project_id: Optional[int] = Field(default=None, ge=1)


class SearchStrategyResponse(BaseModel):
    chinese_query: str
    english_query: str
    chinese_keywords: List[str] = Field(default_factory=list)
    english_keywords: List[str] = Field(default_factory=list)
    exclusions: List[str] = Field(default_factory=list)
    explanation: List[str] = Field(default_factory=list)
    mode: str = "deepseek"
    usage: Dict[str, Any] = Field(default_factory=dict)


class DiscussionPoint(BaseModel):
    title: str
    detail: str


class ResearchDiscussionRequest(BaseModel):
    project_id: int = Field(ge=1)
    question: str = Field(min_length=10, max_length=5000)
    mode: str = Field(
        default="research_question",
        pattern="^(research_question|literature_gap|experiment_review|group_meeting|writing_review)$",
    )
    include_evidence: bool = True
    include_policies: bool = True
    policy_ids: List[str] = Field(default_factory=list, max_length=20)


class ResearchDiscussionResponse(BaseModel):
    answer: str
    points: List[DiscussionPoint] = Field(default_factory=list)
    evidence_refs: List[str] = Field(default_factory=list)
    uncertainties: List[str] = Field(default_factory=list)
    next_actions: List[str] = Field(default_factory=list)
    mode: str = "deepseek-grounded"
    usage: Dict[str, Any] = Field(default_factory=dict)


class ProviderCredentialRequest(BaseModel):
    api_key: str = Field(default="", max_length=4096)
    base_url: str = Field(default="", max_length=2000)
    fast_model: str = Field(default="", max_length=160)
    quality_model: str = Field(default="", max_length=160)
    enabled: bool = True
    priority: int = Field(default=100, ge=1, le=999)


class ModelRoutingRequest(BaseModel):
    mode: str = Field(default="balanced", pattern="^(economy|balanced|quality)$")
    primary_provider: str = Field(default="", max_length=80)
    fallback_enabled: bool = True


class EvidenceItem(BaseModel):
    claim: str
    quote: str
    location: str = "abstract"


class KeyAnswerPoint(BaseModel):
    title: str
    detail: str
    locations: List[str] = Field(default_factory=list)


class KeyQuestionAnswer(BaseModel):
    key: str
    question: str
    answer: str
    verdict: str = "需要核验"
    points: List[KeyAnswerPoint] = Field(default_factory=list)
    evidence: List[EvidenceItem] = Field(default_factory=list)


class DocumentParseInfo(BaseModel):
    filename: str = ""
    pages_total: int = 0
    pages_parsed: int = 0
    char_count: int = 0
    method: str = "text_input"
    quality: str = "unknown"
    quality_score: float = 0.0
    detected_language: str = "unknown"
    ocr_used: bool = False
    ocr_available: bool = False
    truncated: bool = False
    sections_found: List[str] = Field(default_factory=list)


class AnalyzeRequest(BaseModel):
    title: str = Field(default="", max_length=1000)
    abstract: str = Field(min_length=20, max_length=100000)
    research_question: str = Field(default="", max_length=2000)
    use_llm: bool = True


class PaperAnalysis(BaseModel):
    core_problem: str
    methods: List[str]
    innovations: List[str]
    findings: List[str]
    limitations: List[str]
    evidence: List[EvidenceItem]
    key_questions: List[KeyQuestionAnswer] = Field(default_factory=list)
    confidence: str
    mode: str
    output_language: str = "zh-CN"
    document: Optional[DocumentParseInfo] = None
    warnings: List[str] = Field(default_factory=list)
    usage: Dict[str, Any] = Field(default_factory=dict)


class JournalMatchRequest(BaseModel):
    title: str = Field(min_length=2, max_length=1000)
    abstract: str = Field(default="", max_length=30000)
    limit: int = Field(default=10, ge=1, le=20)
    papers: List[Paper] = Field(default_factory=list, max_length=100)


class JournalRecommendation(BaseModel):
    journal: str
    issn: List[str] = Field(default_factory=list)
    score: float
    topical_fit: float
    evidence_count: int
    median_year: Optional[int] = None
    citation_signal: float = 0.0
    reasons: List[str]
    evidence_dois: List[str] = Field(default_factory=list)
    caveats: List[str] = Field(default_factory=list)


class Policy(BaseModel):
    id: str
    title: str
    issuer: str
    published_at: str
    url: HttpUrl
    summary: str
    signals: List[str]
    tags: List[str]
    source_tier: str = "official"


class PolicySource(BaseModel):
    id: str
    sector: str
    authority: str
    portal_name: str
    portal_url: HttpUrl
    scope: str
    keywords: List[str] = Field(default_factory=list)
    update_method: str = "official_portal"


class PolicySyncRequest(BaseModel):
    source_ids: List[str] = Field(default_factory=lambda: ["state-council"], max_length=5)


class PolicyCandidateReview(BaseModel):
    action: str = Field(pattern="^(approve|reject)$")
    title: str = Field(default="", max_length=1000)
    issuer: str = Field(default="", max_length=300)
    published_at: str = Field(default="", max_length=30)
    url: str = Field(default="", max_length=3000)
    summary: str = Field(default="", max_length=5000)
    signals: List[str] = Field(default_factory=list, max_length=20)
    tags: List[str] = Field(default_factory=list, max_length=30)


class LoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=500)


class AuthEmailRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        cleaned = value.strip().casefold()
        if cleaned.count("@") != 1 or "." not in cleaned.rsplit("@", 1)[1]:
            raise ValueError("请输入有效邮箱地址")
        return cleaned


class AuthVerifyRequest(AuthEmailRequest):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class IdeaRequest(BaseModel):
    existing_work: str = Field(min_length=20, max_length=30000)
    research_goal: str = Field(default="", max_length=5000)
    keywords: List[str] = Field(default_factory=list, max_length=20)
    papers: List[Paper] = Field(default_factory=list, max_length=20)
    policy_ids: List[str] = Field(default_factory=list, max_length=20)
    use_llm: bool = True


class WorkDocumentResponse(BaseModel):
    filename: str
    format: str
    text: str
    char_count: int
    truncated: bool = False
    warnings: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class IdeaCandidate(BaseModel):
    title: str
    research_question: str
    hypothesis: str
    proposed_method: List[str]
    novelty: List[str]
    policy_alignment: List[str]
    evidence: List[str]
    risks: List[str]
    first_validation: List[str]


class IdeaResponse(BaseModel):
    candidates: List[IdeaCandidate]
    mode: str
    warnings: List[str] = Field(default_factory=list)
    usage: Dict[str, Any] = Field(default_factory=dict)


class LibraryItemCreate(BaseModel):
    kind: str = Field(pattern="^(paper|policy|analysis|idea|discussion)$")
    external_id: str = Field(min_length=1, max_length=500)
    title: str = Field(min_length=1, max_length=2000)
    payload: Dict[str, Any]
    note: str = Field(default="", max_length=10000)
    project_id: Optional[int] = Field(default=None, ge=1)


class LibraryItem(LibraryItemCreate):
    id: int
    created_at: str


class ExportRequest(BaseModel):
    title: str = Field(default="Research brief", max_length=1000)
    query: str = Field(default="", max_length=2000)
    papers: List[Paper] = Field(default_factory=list, max_length=100)
    analyses: List[PaperAnalysis] = Field(default_factory=list, max_length=20)
    ideas: List[IdeaCandidate] = Field(default_factory=list, max_length=20)
    policies: List[Policy] = Field(default_factory=list, max_length=50)


class BibliographyExportRequest(BaseModel):
    format: str = Field(default="bibtex", pattern="^(bibtex|ris)$")
    papers: List[Paper] = Field(min_length=1, max_length=200)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    research_question: str = Field(default="", max_length=3000)
    description: str = Field(default="", max_length=10000)


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=160)
    research_question: Optional[str] = Field(default=None, max_length=3000)
    description: Optional[str] = Field(default=None, max_length=10000)
    status: Optional[str] = Field(
        default=None, pattern="^(active|paused|completed|archived)$"
    )


class Project(ProjectCreate):
    id: int
    status: str
    evidence_count: int = 0
    search_count: int = 0
    created_at: str
    updated_at: str


class SearchRun(BaseModel):
    id: int
    project_id: Optional[int] = None
    query: str
    sources: List[str]
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    english_query: str = ""
    language: str = "any"
    has_abstract: Optional[bool] = None
    open_access_only: bool = False
    min_citations: int = 0
    sort_by: str = "relevance"
    requested_limit: int
    result_count: int
    source_status: Dict[str, str]
    cache_hit: bool
    elapsed_ms: int
    created_at: str
