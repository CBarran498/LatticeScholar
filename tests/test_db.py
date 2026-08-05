from latticescholar.db import Database
from latticescholar.models import LibraryItemCreate


def test_cache_roundtrip_and_library_crud(tmp_path):
    db = Database(tmp_path / "test.db")
    db.set_cache("key", {"value": 1}, 60)
    assert db.get_cache("key") == {"value": 1}

    item = db.add_library_item(
        LibraryItemCreate(kind="paper", external_id="10.1/example", title="Paper", payload={"a": 1})
    )
    assert item.id > 0
    assert db.list_library_items("paper")[0].payload == {"a": 1}
    assert db.delete_library_item(item.id) is True
    assert db.list_library_items() == []


def test_library_upsert_keeps_single_record(tmp_path):
    db = Database(tmp_path / "test.db")
    first = LibraryItemCreate(kind="policy", external_id="p1", title="Old", payload={})
    second = LibraryItemCreate(kind="policy", external_id="p1", title="New", payload={"v": 2})
    db.add_library_item(first)
    db.add_library_item(second)
    items = db.list_library_items()
    assert len(items) == 1
    assert items[0].title == "New"


def test_projects_search_history_and_project_evidence(tmp_path):
    db = Database(tmp_path / "test.db")
    project = db.create_project(7, "可信医疗AI", "如何降低临床模型外部验证成本？")
    assert project["evidence_count"] == 0
    db.record_search(
        7,
        {
            "query": "external validation clinical AI",
            "sources": ["pubmed"],
            "limit": 20,
            "project_id": project["id"],
        },
        12,
        {"pubmed": "ok (12)"},
        False,
        321,
    )
    db.add_library_item(
        LibraryItemCreate(
            kind="paper",
            external_id="10.1/project",
            title="Project paper",
            payload={"title": "Project paper"},
            project_id=project["id"],
        ),
        owner_id=7,
    )
    refreshed = db.get_project(project["id"], 7)
    assert refreshed["search_count"] == 1
    assert refreshed["evidence_count"] == 1
    assert db.list_search_runs(7, project["id"])[0]["result_count"] == 12
    assert db.list_library_items(owner_id=7, project_id=project["id"])[0].project_id == project["id"]
    assert db.get_project(project["id"], 8) is None
    assert db.delete_project(project["id"], 7) is True
    assert db.list_library_items(owner_id=7)[0].project_id is None


def test_policy_candidate_version_and_review_lifecycle(tmp_path):
    db = Database(tmp_path / "test.db")
    candidate = {
        "source_id": "state-council",
        "external_id": "demo",
        "title": "关于推进科研数据开放的指导意见",
        "issuer": "国务院",
        "published_at": "2026-08-01",
        "url": "https://www.gov.cn/zhengce/demo.html",
        "summary": "自动发现，等待审核。",
        "signals": [],
        "tags": ["科研数据"],
        "content_hash": "hash-one",
        "raw": {},
    }
    assert db.upsert_policy_candidate(candidate) == "new"
    assert db.upsert_policy_candidate(candidate) == "unchanged"
    reviewed = db.review_policy_candidate(
        1,
        "approve",
        {
            **candidate,
            "summary": "该政策提出完善科研数据开放共享和安全治理机制。",
            "signals": ["科研数据开放"],
        },
        reviewer_id=9,
    )
    assert reviewed["status"] == "approved"
    assert len(db.approved_policies()) == 1
    candidate["title"] = "关于推进科研数据开放的指导意见（修订）"
    candidate["content_hash"] = "hash-two"
    assert db.upsert_policy_candidate(candidate) == "changed"
    assert db.list_policy_candidates("pending")[0]["title"].endswith("（修订）")
