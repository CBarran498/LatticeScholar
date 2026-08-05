from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings, settings
from .db import Database
from .models import (
    AdminGrantRequest,
    AnalyzeRequest,
    AuthEmailRequest,
    AuthVerifyRequest,
    BibliographyExportRequest,
    DocumentParseInfo,
    ExportRequest,
    IdeaRequest,
    IdeaResponse,
    JournalMatchRequest,
    JournalRecommendation,
    LibraryItem,
    LibraryItemCreate,
    LoginRequest,
    ModelRoutingRequest,
    PaperAnalysis,
    Policy,
    PolicyCandidateReview,
    PolicySource,
    PolicySyncRequest,
    Project,
    ProjectCreate,
    ProjectUpdate,
    ProviderCredentialRequest,
    ResearchDiscussionRequest,
    ResearchDiscussionResponse,
    SearchRequest,
    SearchResponse,
    SearchRun,
    SearchStrategyRequest,
    SearchStrategyResponse,
    WorkDocumentResponse,
)
from .services.accounts import (
    AccountService,
    AuthenticationError,
    QuotaExceeded,
    UpgradeRequired,
)
from .services.analyzer import AnalyzerService
from .services.auth import AccessManager
from .services.billing import BillingError, BillingService
from .services.document_import import DocumentImportError, extract_document
from .services.exporter import export_bibtex, export_markdown, export_ris
from .services.ideas import IdeaService
from .services.importer import BibliographyImportError, import_bibliography
from .services.journals import JournalService
from .services.literature import LiteratureService
from .services.llm import LLMService, LLMUnavailable
from .services.pdf_parser import PDFParseError, PDFTextUnavailable, parse_pdf
from .services.policies import PolicyService
from .services.policy_sync import PolicySyncService, scheduled_policy_sync
from .services.provider_vault import ProviderVault, ProviderVaultError
from .services.research_assistant import ResearchAssistantService
from .services.sources import ScholarlySources
from .services.updates import UpdateService


def create_app(config: Optional[Settings] = None) -> FastAPI:
    config = config or settings
    config.ensure_directories()
    db = Database(config.database_path)
    policies = PolicyService(config, db)
    provider_vault = ProviderVault(config, db)
    llm = LLMService(config, provider_vault)
    research_assistant = ResearchAssistantService(llm)
    access = AccessManager(config.access_password, config.session_secret)
    accounts = AccountService(config, db)
    billing = BillingService(config, db)
    policy_sync = PolicySyncService(config, db, policies)
    updates = UpdateService(config, db)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        sources = ScholarlySources(config)
        app.state.sources = sources
        app.state.literature = LiteratureService(config, db, sources)
        app.state.analyzer = AnalyzerService(llm)
        app.state.journals = JournalService(sources)
        app.state.ideas = IdeaService(llm, policies)
        app.state.research_assistant = research_assistant
        app.state.policy_sync = policy_sync
        app.state.updates = updates
        sync_task = None
        if config.policy_sync_interval_hours > 0:
            sync_ids = [
                value.strip()
                for value in config.policy_sync_source_ids.split(",")
                if value.strip()
            ]
            sync_task = asyncio.create_task(
                scheduled_policy_sync(
                    policy_sync, sync_ids, config.policy_sync_interval_hours
                )
            )
        try:
            yield
        finally:
            if sync_task:
                sync_task.cancel()
                with suppress(asyncio.CancelledError):
                    await sync_task
            await sources.close()

    app = FastAPI(
        title="LatticeScholar API",
        version=config.app_version,
        description="Local-first, evidence-grounded research intelligence workspace.",
        docs_url="/api/docs",
        redoc_url=None,
        lifespan=lifespan,
    )

    def owner_id(request: Request) -> int:
        return request.state.user["id"] if accounts.enabled else 0

    def require_owned_project(project_id: int, request: Request) -> dict:
        project = db.get_project(project_id, owner_id(request))
        if not project:
            raise HTTPException(status_code=404, detail="科研项目不存在或不属于当前账号")
        return project

    def require_policy_admin(request: Request) -> int:
        if not accounts.enabled:
            return 0
        if not request.state.user or request.state.user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="仅管理员可以同步和审核政策")
        return int(request.state.user["id"])

    def model_user_id(request: Request) -> str:
        return f"lattice_u_{owner_id(request)}"

    def record_model_usage(request: Request, usage: dict) -> None:
        db.record_llm_run(owner_id(request), usage)

    @app.middleware("http")
    async def access_control(request: Request, call_next):
        request.state.user = None
        public_api = {
            "/api/health",
            "/api/auth/status",
            "/api/auth/login",
            "/api/auth/request-code",
            "/api/auth/verify-code",
            "/api/auth/logout",
            "/api/billing/plans",
            "/api/billing/webhook/stripe",
        }
        if accounts.enabled:
            request.state.user = accounts.user_from_token(
                request.cookies.get(accounts.cookie_name, "")
            )
            if (
                request.url.path.startswith("/api/")
                and request.url.path not in public_api
                and request.state.user is None
            ):
                return JSONResponse(status_code=401, content={"detail": "请使用邮箱登录后继续"})
        elif access.required and request.url.path.startswith("/api/") and request.url.path not in public_api:
            if not access.valid(request.cookies.get(access.cookie_name, "")):
                return JSONResponse(status_code=401, content={"detail": "请先登录后使用科研工作台"})
        return await call_next(request)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'"
        )
        return response

    @app.exception_handler(Exception)
    async def unhandled_error(_: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal error", "type": type(exc).__name__},
        )

    @app.exception_handler(UpgradeRequired)
    async def upgrade_required(_: Request, exc: UpgradeRequired):
        return JSONResponse(status_code=402, content={"detail": str(exc), "code": "upgrade_required"})

    @app.exception_handler(QuotaExceeded)
    async def quota_exceeded(_: Request, exc: QuotaExceeded):
        return JSONResponse(status_code=429, content={"detail": str(exc), "code": "quota_exceeded"})

    @app.get("/api/health")
    async def health() -> dict:
        return {
            "status": "ok",
            "app": config.app_name,
            "version": config.app_version,
            "database": "ready",
            "policy_records": len(policies.list()),
            "policy_source_portals": len(policies.sources()),
            "policy_sync": db.policy_sync_status(),
        }

    @app.get("/api/auth/status")
    async def auth_status(request: Request) -> dict:
        if accounts.enabled:
            user = accounts.user_from_token(request.cookies.get(accounts.cookie_name, ""))
            return {
                "mode": "accounts",
                "required": True,
                "authenticated": bool(user),
                "user": accounts.public_user(user) if user else None,
                "dev_auth": config.dev_auth,
            }
        authenticated = not access.required or access.valid(
            request.cookies.get(access.cookie_name, "")
        )
        return {
            "mode": "shared" if access.required else "open",
            "required": access.required,
            "authenticated": authenticated,
        }

    @app.post("/api/auth/request-code")
    async def request_auth_code(payload: AuthEmailRequest) -> dict:
        if not accounts.enabled:
            raise HTTPException(status_code=409, detail="当前不是邮箱账号模式")
        try:
            preview = accounts.request_code(payload.email)
        except AuthenticationError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        result = {"sent": True, "expires_in": 600}
        if preview:
            result["dev_code"] = preview
        return result

    @app.post("/api/auth/verify-code")
    async def verify_auth_code(payload: AuthVerifyRequest) -> JSONResponse:
        if not accounts.enabled:
            raise HTTPException(status_code=409, detail="当前不是邮箱账号模式")
        try:
            user = accounts.verify_code(payload.email, payload.code)
        except AuthenticationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        response = JSONResponse({"authenticated": True, "user": accounts.public_user(user)})
        response.set_cookie(
            accounts.cookie_name,
            accounts.issue_session(user["id"]),
            max_age=30 * 24 * 60 * 60,
            httponly=True,
            secure=config.secure_cookies,
            samesite="lax",
        )
        return response

    @app.post("/api/auth/login")
    async def login(payload: LoginRequest) -> JSONResponse:
        if accounts.enabled:
            raise HTTPException(status_code=409, detail="请使用邮箱验证码登录")
        if access.required and not access.check_password(payload.password):
            raise HTTPException(status_code=401, detail="访问密码不正确")
        response = JSONResponse({"authenticated": True})
        response.set_cookie(
            access.cookie_name,
            access.issue(),
            max_age=12 * 60 * 60,
            httponly=True,
            secure=config.secure_cookies,
            samesite="strict",
        )
        return response

    @app.post("/api/auth/logout")
    async def logout() -> JSONResponse:
        response = JSONResponse({"authenticated": False})
        response.delete_cookie(access.cookie_name)
        response.delete_cookie(accounts.cookie_name)
        return response

    @app.get("/api/account")
    async def account(request: Request) -> dict:
        if not accounts.enabled:
            return {
                "mode": "community",
                "entitlement": accounts.entitlement(None),
                "usage": {},
            }
        return accounts.public_user(request.state.user)

    @app.get("/api/projects", response_model=List[Project])
    async def projects(
        request: Request, include_archived: bool = Query(default=False)
    ) -> List[Project]:
        return [
            Project.model_validate(item)
            for item in db.list_projects(owner_id(request), include_archived)
        ]

    @app.post("/api/projects", response_model=Project)
    async def create_project(payload: ProjectCreate, request: Request) -> Project:
        return Project.model_validate(
            db.create_project(
                owner_id(request), payload.name, payload.research_question, payload.description
            )
        )

    @app.get("/api/projects/{project_id}", response_model=Project)
    async def project(project_id: int, request: Request) -> Project:
        return Project.model_validate(require_owned_project(project_id, request))

    @app.patch("/api/projects/{project_id}", response_model=Project)
    async def update_project(
        project_id: int, payload: ProjectUpdate, request: Request
    ) -> Project:
        require_owned_project(project_id, request)
        updated = db.update_project(
            project_id, owner_id(request), payload.model_dump(exclude_unset=True)
        )
        return Project.model_validate(updated)

    @app.delete("/api/projects/{project_id}")
    async def delete_project(project_id: int, request: Request) -> dict:
        if not db.delete_project(project_id, owner_id(request)):
            raise HTTPException(status_code=404, detail="科研项目不存在或不属于当前账号")
        return {"deleted": True, "evidence_preserved": True}

    @app.get("/api/search-history", response_model=List[SearchRun])
    async def search_history(
        request: Request,
        project_id: Optional[int] = Query(default=None, ge=1),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> List[SearchRun]:
        if project_id:
            require_owned_project(project_id, request)
        return [
            SearchRun.model_validate(item)
            for item in db.list_search_runs(owner_id(request), project_id, limit)
        ]

    @app.delete("/api/search-history/{run_id}")
    async def delete_search_history(run_id: int, request: Request) -> dict:
        if not db.delete_search_run(run_id, owner_id(request)):
            raise HTTPException(status_code=404, detail="检索记录不存在")
        return {"deleted": True}

    @app.get("/api/admin/grants")
    async def list_admin_grants(request: Request) -> list:
        if not request.state.user or request.state.user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="仅管理员可以查看赠送权益")
        return db.list_grants()

    @app.post("/api/admin/grants")
    async def create_admin_grant(payload: AdminGrantRequest, request: Request) -> dict:
        if not request.state.user or request.state.user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="仅管理员可以赠送权益")
        if payload.expires_at:
            try:
                datetime.fromisoformat(payload.expires_at.replace("Z", "+00:00"))
            except ValueError as exc:
                raise HTTPException(status_code=422, detail="到期时间必须是 ISO 8601 格式") from exc
        return db.upsert_grant(
            payload.email, payload.expires_at, payload.reason, request.state.user["id"]
        )

    @app.delete("/api/admin/grants/{email}")
    async def remove_admin_grant(email: str, request: Request) -> dict:
        if not request.state.user or request.state.user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="仅管理员可以撤销赠送权益")
        if not db.delete_grant(email.strip().casefold()):
            raise HTTPException(status_code=404, detail="赠送记录不存在")
        return {"deleted": True}

    @app.get("/api/billing/plans")
    async def billing_plans() -> dict:
        return billing.plans()

    @app.get("/api/update/check")
    async def update_check() -> dict:
        return await updates.check()

    @app.post("/api/billing/checkout")
    async def billing_checkout(request: Request) -> dict:
        if not request.state.user:
            raise HTTPException(status_code=409, detail="托管订阅需要启用邮箱账号模式")
        try:
            return {"url": await billing.create_checkout(request.state.user)}
        except BillingError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/billing/portal")
    async def billing_portal(request: Request) -> dict:
        if not request.state.user:
            raise HTTPException(status_code=409, detail="托管订阅需要启用邮箱账号模式")
        try:
            return {"url": await billing.create_portal(request.state.user)}
        except BillingError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/billing/webhook/stripe")
    async def stripe_webhook(request: Request) -> dict:
        payload = await request.body()
        try:
            event = billing.verify_event(payload, request.headers.get("Stripe-Signature", ""))
            processed = billing.process_event(event)
        except BillingError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"received": True, "processed": processed}

    @app.get("/api/config")
    async def public_config(request: Request) -> dict:
        return {
            "app_name": config.app_name,
            "version": config.app_version,
            "sources": {
                "crossref": {"enabled": True, "identified": bool(config.crossref_email)},
                "semantic_scholar": {
                    "enabled": True,
                    "authenticated": bool(config.semantic_scholar_api_key),
                },
                "openalex": {"enabled": True, "authenticated": bool(config.openalex_api_key)},
                "arxiv": {"enabled": True},
                "pubmed": {
                    "enabled": True,
                    "authenticated": bool(config.ncbi_api_key),
                },
                "web_of_science": {
                    "enabled": bool(config.wos_api_key),
                    "authenticated": bool(config.wos_api_key),
                },
            },
            "llm": {
                **llm.status(owner_id(request)),
                "model": llm.model_for_task("paper_analysis") if llm.enabled else None,
            },
            "auth_mode": "accounts" if accounts.enabled else ("shared" if access.required else "open"),
            "billing": {
                "enabled": config.billing_enabled,
                "ready": billing.ready,
                "provider": config.billing_provider,
            },
            "license": "Apache-2.0",
            "repository_url": config.repository_url,
            "privacy": "Open-source core. Hosted searches send query terms to selected sources.",
        }

    @app.get("/api/llm/status")
    async def llm_status(request: Request) -> dict:
        model_status = llm.status(owner_id(request))
        routing = model_status.get("routing_settings") or {}
        active_by_id = {
            item["id"]: item for item in model_status.get("providers") or [] if item["enabled"]
        }
        primary = active_by_id.get(routing.get("primary_provider"))
        fast_model = (primary or {}).get("fast_model") or model_status.get("fast_model")
        quality_model = (primary or {}).get("quality_model") or model_status.get("reasoning_model")
        return {
            **model_status,
            "usage": db.llm_usage_summary(owner_id(request)),
            "task_routes": [
                {"task": "检索式生成", "model": fast_model, "quality_gate": "双语术语完整性"},
                {"task": "论文深度解剖", "model": quality_model, "quality_gate": "中文结构 + 页码证据"},
                {"task": "Idea Lab", "model": quality_model, "quality_gate": "证据与政策引用边界"},
                {"task": "课题研讨", "model": quality_model, "quality_gate": "证据编号白名单"},
            ],
            "configuration": {
                "mode": "encrypted_byok",
                "key_returned_to_browser": False,
                "custom_remote_hosts_allowed": config.allow_custom_model_hosts,
            },
        }

    @app.get("/api/model-providers")
    async def list_model_providers(request: Request) -> dict:
        return {
            "providers": provider_vault.list_public(owner_id(request)),
            "routing": provider_vault.routing(owner_id(request)),
            "security": provider_vault.security_status(),
        }

    @app.put("/api/model-providers/{provider_id}")
    async def save_model_provider(
        provider_id: str, payload: ProviderCredentialRequest, request: Request
    ) -> dict:
        accounts.require_pro(request.state.user, "模型服务配置")
        try:
            return provider_vault.save(
                owner_id(request),
                provider_id,
                api_key=payload.api_key,
                base_url=payload.base_url,
                fast_model=payload.fast_model,
                quality_model=payload.quality_model,
                enabled=payload.enabled,
                priority=payload.priority,
            )
        except (ProviderVaultError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.delete("/api/model-providers/{provider_id}")
    async def delete_model_provider(provider_id: str, request: Request) -> dict:
        accounts.require_pro(request.state.user, "模型服务配置")
        try:
            deleted = provider_vault.delete(owner_id(request), provider_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"deleted": deleted}

    @app.post("/api/model-providers/{provider_id}/test")
    async def test_model_provider(provider_id: str, request: Request) -> dict:
        accounts.require_pro(request.state.user, "模型连接测试")
        try:
            result = await llm.test_connection(
                model_user_id(request), owner_id=owner_id(request), provider_id=provider_id
            )
        except (LLMUnavailable, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        record_model_usage(request, result.get("usage") or {})
        return result

    @app.put("/api/model-routing")
    async def save_model_routing(payload: ModelRoutingRequest, request: Request) -> dict:
        accounts.require_pro(request.state.user, "模型智能路由")
        try:
            return provider_vault.save_routing(
                owner_id(request), payload.mode, payload.primary_provider, payload.fallback_enabled
            )
        except (ProviderVaultError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/llm/test")
    async def test_llm(request: Request) -> dict:
        accounts.require_pro(request.state.user, "模型连接测试")
        try:
            result = await llm.test_connection(
                model_user_id(request), owner_id=owner_id(request)
            )
        except LLMUnavailable as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        record_model_usage(request, result.get("usage") or {})
        return result

    @app.post("/api/search/strategy", response_model=SearchStrategyResponse)
    async def create_search_strategy(
        payload: SearchStrategyRequest, request: Request
    ) -> SearchStrategyResponse:
        accounts.require_pro(request.state.user, "DeepSeek 中英文检索策略")
        project = require_owned_project(payload.project_id, request) if payload.project_id else None
        try:
            result = await request.app.state.research_assistant.search_strategy(
                payload, project, model_user_id(request), owner_id(request)
            )
        except LLMUnavailable as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        record_model_usage(request, result.usage)
        return result

    @app.post("/api/discussions", response_model=ResearchDiscussionResponse)
    async def research_discussion(
        payload: ResearchDiscussionRequest, request: Request
    ) -> ResearchDiscussionResponse:
        accounts.require_pro(request.state.user, "DeepSeek 课题研讨")
        project = require_owned_project(payload.project_id, request)
        evidence = (
            db.list_library_items(owner_id=owner_id(request), project_id=payload.project_id)
            if payload.include_evidence
            else []
        )
        policy_context = [
            {
                "id": item.id,
                "title": item.title,
                "issuer": item.issuer,
                "date": item.published_at,
                "summary": item.summary,
                "url": str(item.url),
            }
            for item in policies.get_many(payload.policy_ids)
        ]
        try:
            result = await request.app.state.research_assistant.discuss(
                payload, project, evidence, policy_context, model_user_id(request), owner_id(request)
            )
        except LLMUnavailable as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        record_model_usage(request, result.usage)
        return result

    @app.get("/api/connectors")
    async def connectors() -> list:
        return [
            {
                "id": "pubmed", "name": "PubMed", "mode": "official_api", "ready": True,
                "coverage": "生物医学与生命科学", "cost": "免费；高频请求建议配置 NCBI_API_KEY",
                "search_url": "https://pubmed.ncbi.nlm.nih.gov/",
                "workflow": "检索、论文解剖、期刊匹配证据、Idea Lab 与证据库",
            },
            {
                "id": "web_of_science", "name": "Web of Science", "mode": "licensed_api",
                "ready": bool(config.wos_api_key), "coverage": "跨学科引文索引与期刊元数据",
                "cost": "需在 Clarivate Developer Portal 注册 Key；套餐有日配额",
                "search_url": "https://www.webofscience.com/", "workflow": "配置 Key 后进入统一检索和全部下游工作流",
            },
            {
                "id": "cnki", "name": "中国知网", "mode": "authorized_or_import", "ready": True,
                "coverage": "中文期刊、学位论文、会议、年鉴等", "cost": "全文与机构数据受订阅授权约束",
                "search_url": "https://kns.cnki.net/kns8s/", "workflow": "原站检索后导出 EndNote/RefWorks/NoteExpress 题录，再导入全部下游工作流",
            },
            {
                "id": "google_scholar", "name": "Google Scholar", "mode": "link_and_import", "ready": True,
                "coverage": "跨学科学术发现与引用追踪", "cost": "官方不提供批量 API，禁止自动抓取",
                "search_url": "https://scholar.google.com/", "workflow": "原站检索并导出 BibTeX/EndNote/RefMan/RefWorks，再导入全部下游工作流",
            },
        ]

    @app.post("/api/search", response_model=SearchResponse)
    async def search(request: SearchRequest, http_request: Request) -> SearchResponse:
        user = http_request.state.user
        if request.project_id:
            require_owned_project(request.project_id, http_request)
        accounts.check_daily(user, "search")
        accounts.validate_sources(user, request.sources)
        if accounts.enabled and not accounts.entitlement(user)["is_pro"]:
            request.limit = min(request.limit, 20)
        result = await http_request.app.state.literature.search(request)
        db.record_search(
            owner_id(http_request),
            request.model_dump(mode="json"),
            len(result.papers),
            result.source_status,
            result.cache_hit,
            result.elapsed_ms,
        )
        accounts.record(user, "search")
        return result

    @app.post("/api/import/bibliography", response_model=SearchResponse)
    async def import_records(
        http_request: Request,
        file: UploadFile = File(...),
        source_name: str = Form(default="Imported record"),
        project_id: Optional[int] = Form(default=None),
    ) -> SearchResponse:
        accounts.require_pro(http_request.state.user, "批量题录导入")
        if project_id:
            require_owned_project(project_id, http_request)
        content = await file.read(5 * 1024 * 1024 + 1)
        if len(content) > 5 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="题录文件超过 5 MB")
        source_name = source_name.strip()[:80] or "Imported record"
        try:
            papers = import_bibliography(file.filename or "records.txt", content, source_name)
        except BibliographyImportError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        merged = http_request.app.state.literature._merge_and_rank("", {"import": papers})
        response = SearchResponse(
            papers=merged,
            source_status={"import": f"ok ({len(merged)})"},
            elapsed_ms=0,
            notices=["题录已在内存中解析；请通过原平台或 DOI 核验摘要、全文与授权状态。"],
        )
        db.record_search(
            owner_id(http_request),
            {
                "query": f"题录导入：{file.filename or source_name}",
                "sources": [source_name],
                "year_from": None,
                "year_to": None,
                "limit": len(merged),
                "project_id": project_id,
            },
            len(merged),
            response.source_status,
            False,
            0,
        )
        return response

    @app.post("/api/analyze", response_model=PaperAnalysis)
    async def analyze(request: AnalyzeRequest, http_request: Request) -> PaperAnalysis:
        user = http_request.state.user
        accounts.check_daily(user, "analysis")
        if request.use_llm:
            accounts.require_pro(user, "模型深度分析")
        result = await http_request.app.state.analyzer.analyze(
            request, model_user_id(http_request), owner_id(http_request)
        )
        record_model_usage(http_request, result.usage)
        accounts.record(user, "analysis")
        return result

    @app.post("/api/analyze/pdf", response_model=PaperAnalysis)
    async def analyze_pdf(
        http_request: Request,
        file: UploadFile = File(...),
        title: str = "",
        research_question: str = "",
        use_llm: bool = True,
    ) -> PaperAnalysis:
        user = http_request.state.user
        accounts.check_daily(user, "analysis")
        if use_llm:
            accounts.require_pro(user, "PDF 模型深度分析")
        if file.content_type not in {"application/pdf", "application/octet-stream"}:
            raise HTTPException(status_code=415, detail="仅支持 PDF 格式文件")
        content = await file.read(15 * 1024 * 1024 + 1)
        if len(content) > 15 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="PDF 文件超过 15 MB 安全上限")
        try:
            parsed = parse_pdf(content, file.filename or "论文.pdf")
        except (PDFTextUnavailable, PDFParseError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        extracted_title = title or parsed.title_candidate or file.filename or ""

        result = await http_request.app.state.analyzer.analyze(
            AnalyzeRequest(
                title=extracted_title,
                abstract=parsed.text,
                research_question=research_question,
                use_llm=use_llm,
            ),
            model_user_id(http_request),
            owner_id(http_request),
        )
        record_model_usage(http_request, result.usage)
        result.document = DocumentParseInfo(
            filename=parsed.filename,
            pages_total=parsed.pages_total,
            pages_parsed=parsed.pages_parsed,
            char_count=parsed.char_count,
            method=parsed.method,
            quality=parsed.quality,
            quality_score=parsed.quality_score,
            detected_language=parsed.detected_language,
            ocr_used=parsed.ocr_used,
            ocr_available=parsed.ocr_available,
            truncated=parsed.truncated,
            sections_found=parsed.sections_found,
        )
        result.warnings.extend(parsed.warnings)
        result.warnings.append(
            "PDF 仅在内存中解析且不会由应用保存；中文解释与原文证据引用分开展示。"
        )
        result.warnings = list(dict.fromkeys(result.warnings))
        accounts.record(user, "analysis")
        return result

    @app.post("/api/journals/match", response_model=List[JournalRecommendation])
    async def match_journals(
        request: JournalMatchRequest, http_request: Request
    ) -> List[JournalRecommendation]:
        user = http_request.state.user
        accounts.check_daily(user, "journal_match")
        result = await http_request.app.state.journals.match(request)
        accounts.record(user, "journal_match")
        return result

    @app.get("/api/policies", response_model=List[Policy])
    async def list_policies(
        q: str = Query(default="", max_length=500), tag: Optional[str] = Query(default=None)
    ) -> List[Policy]:
        return policies.list(q, tag)

    @app.get("/api/policy-sources", response_model=List[PolicySource])
    async def list_policy_sources(q: str = Query(default="", max_length=200)) -> List[PolicySource]:
        return policies.sources(q)

    @app.get("/api/policy-sync/status")
    async def policy_sync_status() -> dict:
        return db.policy_sync_status()

    @app.get("/api/admin/policy-candidates")
    async def policy_candidates(
        request: Request,
        status: str = Query(default="pending", pattern="^(pending|approved|rejected|)$"),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> list:
        require_policy_admin(request)
        return db.list_policy_candidates(status, limit)

    @app.post("/api/admin/policies/sync")
    async def sync_policies(payload: PolicySyncRequest, request: Request) -> dict:
        require_policy_admin(request)
        try:
            runs = await request.app.state.policy_sync.sync(payload.source_ids)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"runs": runs, "status": db.policy_sync_status()}

    @app.post("/api/admin/policy-candidates/{candidate_id}/review")
    async def review_policy(
        candidate_id: int, payload: PolicyCandidateReview, request: Request
    ) -> dict:
        reviewer_id = require_policy_admin(request)
        candidate = db.get_policy_candidate(candidate_id)
        if not candidate:
            raise HTTPException(status_code=404, detail="政策候选不存在")
        if payload.action == "reject":
            return db.review_policy_candidate(candidate_id, "reject", {}, reviewer_id)
        record = {
            "title": payload.title.strip() or candidate["title"],
            "issuer": payload.issuer.strip() or candidate["issuer"],
            "published_at": payload.published_at.strip() or candidate["published_at"],
            "url": payload.url.strip() or candidate["url"],
            "summary": payload.summary.strip() or candidate["summary"],
            "signals": payload.signals or candidate["signals"],
            "tags": payload.tags or candidate["tags"],
        }
        try:
            datetime.fromisoformat(record["published_at"])
            Policy(
                id=f"dynamic-{candidate_id}",
                source_tier="official-reviewed",
                **record,
            )
        except (ValueError, TypeError) as exc:
            raise HTTPException(
                status_code=422,
                detail="批准前必须填写有效发布日期、官方链接和完整政策信息",
            ) from exc
        if len(record["summary"]) < 20:
            raise HTTPException(status_code=422, detail="政策摘要至少需要20个字符")
        return db.review_policy_candidate(candidate_id, "approve", record, reviewer_id)

    @app.post("/api/ideas/import", response_model=WorkDocumentResponse)
    async def import_idea_work(file: UploadFile = File(...)) -> WorkDocumentResponse:
        content = await file.read(12 * 1024 * 1024 + 1)
        if len(content) > 12 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="文件超过 12 MB 安全上限")
        try:
            imported = extract_document(file.filename or "document", content)
        except DocumentImportError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return WorkDocumentResponse(**vars(imported))

    @app.post("/api/ideas", response_model=IdeaResponse)
    async def generate_ideas(request: IdeaRequest, http_request: Request) -> IdeaResponse:
        user = http_request.state.user
        accounts.check_daily(user, "idea")
        if request.use_llm:
            accounts.require_pro(user, "模型增强 Idea Lab")
        result = await http_request.app.state.ideas.generate(
            request, model_user_id(http_request), owner_id(http_request)
        )
        record_model_usage(http_request, result.usage)
        accounts.record(user, "idea")
        return result

    @app.get("/api/library", response_model=List[LibraryItem])
    async def library(
        request: Request,
        kind: Optional[str] = Query(default=None),
        project_id: Optional[int] = Query(default=None, ge=1),
    ) -> List[LibraryItem]:
        if kind and kind not in {"paper", "policy", "analysis", "idea", "discussion"}:
            raise HTTPException(status_code=422, detail="Unsupported library kind")
        if project_id:
            require_owned_project(project_id, request)
        return db.list_library_items(kind, owner_id(request), project_id)

    @app.post("/api/library", response_model=LibraryItem)
    async def save_library(item: LibraryItemCreate, request: Request) -> LibraryItem:
        accounts.check_library(request.state.user)
        if item.project_id:
            require_owned_project(item.project_id, request)
        return db.add_library_item(item, owner_id(request))

    @app.patch("/api/library/{item_id}")
    async def update_library_note(item_id: int, request: Request) -> dict:
        body = await request.json()
        note = str(body.get("note", ""))[:10000]
        if not db.update_library_note(item_id, owner_id(request), note):
            raise HTTPException(status_code=404, detail="证据条目不存在")
        return {"updated": True, "note": note}

    @app.delete("/api/library/{item_id}")
    async def delete_library(item_id: int, request: Request) -> dict:
        if not db.delete_library_item(item_id, owner_id(request)):
            raise HTTPException(status_code=404, detail="Library item not found")
        return {"deleted": True}

    @app.post("/api/export", response_class=PlainTextResponse)
    async def export(request: ExportRequest) -> PlainTextResponse:
        return PlainTextResponse(
            export_markdown(request),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="latticescholar-brief.md"'},
        )

    @app.post("/api/export/bibliography", response_class=PlainTextResponse)
    async def export_bibliography(payload: BibliographyExportRequest) -> PlainTextResponse:
        if payload.format == "ris":
            content = export_ris(payload.papers)
            media_type = "application/x-research-info-systems; charset=utf-8"
            filename = "latticescholar-evidence.ris"
        else:
            content = export_bibtex(payload.papers)
            media_type = "application/x-bibtex; charset=utf-8"
            filename = "latticescholar-evidence.bib"
        return PlainTextResponse(
            content,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    app.mount("/", StaticFiles(directory=str(config.static_dir), html=True), name="static")
    return app


app = create_app()
