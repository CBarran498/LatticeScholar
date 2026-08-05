from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from latticescholar.config import Settings
from latticescholar.db import Database
from latticescholar.main import create_app
from latticescholar.models import Paper, SearchResponse
from tests.test_pdf_parser import make_research_pdf


def make_client(tmp_path):
    config = Settings(data_dir=tmp_path, llm_provider="none", auth_mode="open")
    return TestClient(create_app(config))


def test_health_config_static_and_policies(tmp_path):
    with make_client(tmp_path) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["policy_records"] >= 8
        assert health.json()["policy_source_portals"] >= 30
        config = client.get("/api/config").json()
        assert config["llm"]["enabled"] is False
        policies = client.get("/api/policies?q=人工智能").json()
        assert policies
        assert len(client.get("/api/policy-sources").json()) >= 30
        connectors = client.get("/api/connectors").json()
        assert {item["id"] for item in connectors} == {
            "pubmed", "web_of_science", "cnki", "google_scholar"
        }
        home = client.get("/")
        assert home.status_code == 200
        assert "LatticeScholar" in home.text


def test_analysis_ideas_library_and_export(tmp_path):
    with make_client(tmp_path) as client:
        analysis = client.post(
            "/api/analyze",
            json={
                "title": "Demo",
                "abstract": "We propose a novel method. Results show better accuracy. Future work needs external validation.",
                "use_llm": False,
            },
        )
        assert analysis.status_code == 200
        assert analysis.json()["mode"] == "heuristic"
        assert analysis.json()["output_language"] == "zh-CN"
        assert len(analysis.json()["key_questions"]) == 4

        pdf_analysis = client.post(
            "/api/analyze/pdf",
            files={"file": ("long-research-paper.pdf", make_research_pdf(), "application/pdf")},
            data={"use_llm": "false"},
        )
        assert pdf_analysis.status_code == 200
        assert pdf_analysis.json()["document"]["pages_parsed"] == 3
        assert pdf_analysis.json()["document"]["method"] == "pdfplumber_layout"
        assert pdf_analysis.json()["output_language"] == "zh-CN"

        ideas = client.post(
            "/api/ideas",
            json={
                "existing_work": "我们已经完成一个轻量模型并在公开数据集进行了实验验证。",
                "use_llm": False,
            },
        )
        assert ideas.status_code == 200
        assert len(ideas.json()["candidates"]) == 3

        imported_work = client.post(
            "/api/ideas/import",
            files={"file": ("前期工作.md", "已完成数据清洗、对照基线和两轮外部验证。".encode(), "text/markdown")},
        )
        assert imported_work.status_code == 200
        assert imported_work.json()["format"] == "Markdown"
        assert "外部验证" in imported_work.json()["text"]

        unsupported_work = client.post(
            "/api/ideas/import",
            files={"file": ("model.bin", b"unsupported binary document", "application/octet-stream")},
        )
        assert unsupported_work.status_code == 422

        saved = client.post(
            "/api/library",
            json={
                "kind": "paper",
                "external_id": "demo",
                "title": "Demo paper",
                "payload": {"title": "Demo paper"},
            },
        )
        assert saved.status_code == 200
        item_id = saved.json()["id"]
        assert len(client.get("/api/library").json()) == 1
        updated = client.patch(f"/api/library/{item_id}", json={"note": "已核对 DOI"})
        assert updated.json()["note"] == "已核对 DOI"
        assert client.delete(f"/api/library/{item_id}").json()["deleted"] is True
        assert client.patch(f"/api/library/{item_id}", json={"note": "missing"}).status_code == 404

        exported = client.post(
            "/api/export",
            json={"title": "Brief", "query": "test", "papers": [], "ideas": []},
        )
        assert exported.status_code == 200
        assert "Verification checklist" in exported.text
        ris = client.post(
            "/api/export/bibliography",
            json={"format": "ris", "papers": [{"id": "p", "title": "Demo"}]},
        )
        assert ris.status_code == 200 and "TY  - JOUR" in ris.text


def test_validation_errors_are_clear(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post("/api/search", json={"query": "x", "sources": ["unknown"]})
        assert response.status_code == 422
        reversed_years = client.post(
            "/api/search",
            json={
                "query": "valid research query",
                "sources": ["crossref"],
                "year_from": 2026,
                "year_to": 2020,
            },
        )
        assert reversed_years.status_code == 422
        invalid_pdf = client.post(
            "/api/analyze/pdf",
            files={"file": ("broken.pdf", b"%PDF invalid", "application/pdf")},
            data={"use_llm": "false"},
        )
        assert invalid_pdf.status_code == 422
        assert any(word in invalid_pdf.json()["detail"] for word in ("PDF", "文字", "损坏"))

        css = client.get("/styles.css")
        assert css.status_code == 200
        assert "overflow-wrap:anywhere" in css.text
        assert ".evidence-trace" in css.text
        assert ".answer-points" in css.text
        app_js = client.get("/app.js")
        assert app_js.status_code == 200
        assert "论文四问" in app_js.text
        assert "展开证据化详细拆解" not in app_js.text
        assert "核对原文依据" in app_js.text


def test_private_access_and_bibliography_import(tmp_path):
    config = Settings(
        data_dir=tmp_path,
        llm_provider="none",
        auth_mode="shared",
        access_password="correct horse battery staple",
        session_secret="test-secret-that-is-long-enough",
    )
    with TestClient(create_app(config)) as client:
        assert client.get("/api/config").status_code == 401
        assert client.post("/api/auth/login", json={"password": "wrong"}).status_code == 401
        assert client.post(
            "/api/auth/login", json={"password": "correct horse battery staple"}
        ).status_code == 200
        project = client.post(
            "/api/projects",
            json={"name": "题录导入项目", "research_question": "如何复用合规导入题录？"},
        ).json()
        imported = client.post(
            "/api/import/bibliography",
            files={"file": ("records.ris", b"TY  - JOUR\nTI  - Imported evidence\nPY  - 2025\nER  -\n")},
            data={"source_name": "中国知网", "project_id": str(project["id"])},
        )
        assert imported.status_code == 200
        assert imported.json()["papers"][0]["sources"] == ["中国知网"]
        history = client.get(f"/api/search-history?project_id={project['id']}").json()
        assert history[0]["query"] == "题录导入：records.ris"


def _email_login(client, email):
    requested = client.post("/api/auth/request-code", json={"email": email})
    assert requested.status_code == 200
    code = requested.json()["dev_code"]
    verified = client.post("/api/auth/verify-code", json={"email": email, "code": code})
    assert verified.status_code == 200
    return verified.json()["user"]


def test_email_accounts_admin_and_user_roles(tmp_path):
    config = Settings(
        data_dir=tmp_path,
        llm_provider="none",
        auth_mode="accounts",
        dev_auth=True,
        session_secret="account-test-secret",
        admin_emails="admin@example.edu",
    )
    app = create_app(config)
    with TestClient(app) as client:
        status = client.get("/api/auth/status").json()
        assert status["mode"] == "accounts"
        assert status["authenticated"] is False

        user = _email_login(client, "researcher@example.edu")
        assert user["entitlement"]["plan"] == "user"
        assert user["entitlement"]["is_pro"] is True
        assert user["role"] == "user"

        client.post("/api/auth/logout")
        admin = _email_login(client, "admin@example.edu")
        assert admin["role"] == "admin"
        assert admin["entitlement"]["plan"] == "admin"


def test_project_workspace_records_reproducible_search_and_exports_citations(tmp_path):
    config = Settings(data_dir=tmp_path, llm_provider="none", auth_mode="open")
    app = create_app(config)
    with TestClient(app) as client:
        project = client.post(
            "/api/projects",
            json={
                "name": "低资源可信AI",
                "research_question": "低资源环境下如何验证模型可靠性？",
            },
        ).json()
        app.state.literature.search = AsyncMock(
            return_value=SearchResponse(
                papers=[
                    Paper(
                        id="demo",
                        title="Reliable AI under resource constraints",
                        authors=["Ada Lovelace"],
                        year=2026,
                        doi="10.1000/reliable",
                        sources=["Crossref"],
                    )
                ],
                source_status={"crossref": "ok (1)"},
                elapsed_ms=25,
            )
        )
        searched = client.post(
            "/api/search",
            json={
                "query": "reliable AI resource constraints",
                "sources": ["crossref"],
                "project_id": project["id"],
            },
        )
        assert searched.status_code == 200
        history = client.get(f"/api/search-history?project_id={project['id']}").json()
        assert history[0]["query"] == "reliable AI resource constraints"
        assert history[0]["sources"] == ["crossref"]
        saved = client.post(
            "/api/library",
            json={
                "kind": "paper",
                "external_id": "10.1000/reliable",
                "title": "Reliable AI under resource constraints",
                "payload": searched.json()["papers"][0],
                "project_id": project["id"],
            },
        )
        assert saved.status_code == 200
        assert client.get(f"/api/projects/{project['id']}").json()["evidence_count"] == 1
        bibtex = client.post(
            "/api/export/bibliography",
            json={"format": "bibtex", "papers": searched.json()["papers"]},
        )
        assert bibtex.status_code == 200
        assert "10.1000/reliable" in bibtex.text


def test_admin_policy_review_publishes_dynamic_policy(tmp_path):
    config = Settings(
        data_dir=tmp_path,
        llm_provider="none",
        auth_mode="accounts",
        dev_auth=True,
        session_secret="policy-admin-test",
        admin_emails="admin@example.edu",
    )
    app = create_app(config)
    db = Database(config.database_path)
    db.upsert_policy_candidate(
        {
            "source_id": "state-council",
            "external_id": "policy-api-demo",
            "title": "关于推进高校科研数据开放的指导意见",
            "issuer": "国务院",
            "published_at": "2026-08-01",
            "url": "https://www.gov.cn/zhengce/policy-api-demo.html",
            "summary": "自动发现，等待审核。",
            "signals": [],
            "tags": ["科研数据"],
            "content_hash": "policy-api-hash",
            "raw": {},
        }
    )
    with TestClient(app) as client:
        _email_login(client, "admin@example.edu")
        candidates = client.get("/api/admin/policy-candidates").json()
        reviewed = client.post(
            f"/api/admin/policy-candidates/{candidates[0]['id']}/review",
            json={
                "action": "approve",
                "published_at": "2026-08-01",
                "summary": "该政策要求完善高校科研数据开放共享、安全治理与成果转化机制。",
                "signals": ["科研数据开放", "安全治理"],
                "tags": ["高校", "科研数据"],
            },
        )
        assert reviewed.status_code == 200
        assert reviewed.json()["status"] == "approved"
        policies = client.get("/api/policies?q=科研数据开放").json()
        assert any(item["source_tier"] == "official-reviewed" for item in policies)
