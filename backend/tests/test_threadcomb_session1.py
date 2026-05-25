"""ThreadComb Session 1 backend tests.

Covers:
- /api/health, /api/
- /api/auth/creator (POST/GET/DELETE) + idempotency + sensitive field stripping
- /api/onboarding/{cid}/step-1, step-2, step-3, /gmail-connect, /status
- /api/auth/session (invalid), /api/auth/me (no auth) → 401
- MongoDB collections, niche_graph seed data, data_classification on creators
- ACTION_POLICY: get_action_policy decisions
"""
import os
import sys
import uuid
import pytest
import requests
from pymongo import MongoClient

# Make backend importable for ACTION_POLICY tests
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from services.action_policy import ActionType, get_action_policy  # noqa: E402

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"
API = f"{BASE_URL}/api"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "threadcomb")


# --------------------------- Fixtures ---------------------------

@pytest.fixture(scope="session")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def mongo_db():
    cli = MongoClient(MONGO_URL)
    return cli[DB_NAME]


@pytest.fixture()
def fresh_creator(client):
    email = f"TEST_{uuid.uuid4().hex[:8]}@threadcomb.dev"
    r = client.post(f"{API}/auth/creator", json={
        "email": email, "name": "Test Creator", "avatar_url": "https://i.pravatar.cc/150",
    })
    assert r.status_code == 200, r.text
    data = r.json()
    cid = data["creator_id"]
    yield {"creator_id": cid, "email": email}
    # cleanup
    try:
        client.delete(f"{API}/auth/creator/{cid}")
    except Exception:
        pass


# --------------------------- Health / Root ---------------------------

class TestHealth:
    def test_health(self, client):
        r = client.get(f"{API}/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["mongo"] is True

    def test_root(self, client):
        r = client.get(f"{API}/")
        assert r.status_code == 200
        body = r.json()
        assert body["service"] == "threadcomb-backend"
        assert "tagline" in body


# --------------------------- Auth: creator direct create ---------------------------

class TestCreatorLifecycle:
    def test_create_creator(self, client):
        email = f"TEST_{uuid.uuid4().hex[:8]}@threadcomb.dev"
        r = client.post(f"{API}/auth/creator", json={
            "email": email, "name": "New User", "avatar_url": None,
        })
        assert r.status_code == 200
        d = r.json()
        assert d["creator_id"].startswith("creator_")
        assert d["onboarding_step"] == 0
        # cleanup
        client.delete(f"{API}/auth/creator/{d['creator_id']}")

    def test_create_creator_idempotent(self, client):
        email = f"TEST_{uuid.uuid4().hex[:8]}@threadcomb.dev"
        r1 = client.post(f"{API}/auth/creator", json={"email": email, "name": "A"})
        r2 = client.post(f"{API}/auth/creator", json={"email": email, "name": "A"})
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json()["creator_id"] == r2.json()["creator_id"]
        client.delete(f"{API}/auth/creator/{r1.json()['creator_id']}")

    def test_get_creator_strips_gmail_secret(self, client, fresh_creator):
        cid = fresh_creator["creator_id"]
        r = client.get(f"{API}/auth/creator/{cid}")
        assert r.status_code == 200
        d = r.json()
        assert d["creator_id"] == cid
        assert "gmail_secret_path" not in d
        assert d["email"] == fresh_creator["email"]

    def test_get_creator_404(self, client):
        r = client.get(f"{API}/auth/creator/creator_nonexistent_xyz")
        assert r.status_code == 404

    def test_delete_creator_returns_counts(self, client):
        email = f"TEST_{uuid.uuid4().hex[:8]}@threadcomb.dev"
        r = client.post(f"{API}/auth/creator", json={"email": email, "name": "DelMe"})
        cid = r.json()["creator_id"]
        d = client.delete(f"{API}/auth/creator/{cid}")
        assert d.status_code == 200
        body = d.json()
        assert body["creator_id"] == cid
        assert "deleted_counts" in body
        assert body["deleted_counts"]["creators"] == 1
        # subsequent fetch is 404
        assert client.get(f"{API}/auth/creator/{cid}").status_code == 404


# --------------------------- Onboarding ---------------------------

class TestOnboarding:
    def test_step1_platform(self, client, fresh_creator):
        cid = fresh_creator["creator_id"]
        r = client.patch(f"{API}/onboarding/{cid}/step-1", json={"platform": "instagram"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["platform_primary"] == "instagram"
        assert d["onboarding_step"] == 1

    def test_step2_niche(self, client, fresh_creator):
        cid = fresh_creator["creator_id"]
        r = client.patch(
            f"{API}/onboarding/{cid}/step-2",
            json={"niche": "beauty", "niche_secondary": ["fashion"]},
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["niche"] == "beauty"
        assert d["niche_secondary"] == ["fashion"]
        assert d["onboarding_step"] == 2

    def test_step3_profile_follower_tier_mapping(self, client, fresh_creator):
        cid = fresh_creator["creator_id"]
        r = client.patch(f"{API}/onboarding/{cid}/step-3", json={
            "handle": "@test", "follower_bucket": "50k_200k",
            "geography": "IN", "language_primary": "en",
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["handle"] == "@test"
        assert d["follower_tier"] == "mid"  # critical mapping
        assert d["geography"] == "IN"
        assert d["onboarding_step"] == 3

    def test_gmail_connect_completes_onboarding(self, client, fresh_creator, mongo_db):
        cid = fresh_creator["creator_id"]
        r = client.post(f"{API}/onboarding/{cid}/gmail-connect")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["gmail_connected"] is True
        assert d["onboarding_step"] == 5
        # verify persistence
        doc = mongo_db.creators.find_one({"creator_id": cid})
        assert doc["gmail_connected"] is True
        assert doc.get("gmail_secret_path")
        assert doc.get("onboarding_completed_at") is not None

    def test_status_endpoint(self, client, fresh_creator):
        cid = fresh_creator["creator_id"]
        r = client.get(f"{API}/onboarding/{cid}/status")
        assert r.status_code == 200
        assert r.json()["creator_id"] == cid

    def test_step1_unknown_creator_404(self, client):
        r = client.patch(f"{API}/onboarding/creator_does_not_exist/step-1",
                         json={"platform": "instagram"})
        assert r.status_code == 404


# --------------------------- Auth: session / me failure paths ---------------------------

class TestAuthFailures:
    def test_session_invalid_returns_401(self, client):
        # Bad session_id should be rejected by upstream and result in 401
        r = client.post(f"{API}/auth/session", json={"session_id": "totally-invalid-xxx"})
        assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text}"

    def test_me_without_cookie_returns_401(self):
        # Use a fresh client without cookies/headers
        r = requests.get(f"{API}/auth/me")
        assert r.status_code == 401


# --------------------------- MongoDB invariants ---------------------------

class TestMongoInvariants:
    def test_all_10_collections_exist(self, mongo_db):
        expected = {"creators", "brands", "deals", "invoices", "skills_map",
                    "agent_actions", "fan_interactions", "fan_profiles",
                    "response_templates", "niche_graph"}
        names = set(mongo_db.list_collection_names())
        missing = expected - names
        assert not missing, f"missing collections: {missing}"

    def test_niche_graph_seed_invariants(self, mongo_db):
        docs = list(mongo_db.niche_graph.find({}))
        assert len(docs) >= 10
        for d in docs:
            assert d.get("data_source") == "pre_training"
            rd = d.get("rate_distribution", {})
            assert rd.get("confidence") == 0.3
            assert d.get("data_classification", {}).get("tier") == "aggregate"
            # Per-spec rate distribution invariants
            p50 = rd["p50"]
            assert abs(rd["p25"] - round(p50 * 0.65, 2)) < 0.01
            assert abs(rd["p75"] - round(p50 * 1.55, 2)) < 0.01

    def test_creator_has_data_classification(self, client, mongo_db):
        email = f"TEST_{uuid.uuid4().hex[:8]}@threadcomb.dev"
        r = client.post(f"{API}/auth/creator", json={"email": email, "name": "DC"})
        cid = r.json()["creator_id"]
        try:
            doc = mongo_db.creators.find_one({"creator_id": cid})
            assert doc is not None
            dc = doc.get("data_classification")
            assert dc is not None
            assert dc.get("tier") == "personal_identifiable"
        finally:
            client.delete(f"{API}/auth/creator/{cid}")


# --------------------------- ACTION_POLICY ---------------------------

class TestActionPolicy:
    def test_send_brand_deal_email_requires_approval(self):
        p = get_action_policy(ActionType.SEND_BRAND_DEAL_EMAIL, confidence=0.9)
        assert p["requires_creator_approval"] is True
        assert p["can_execute"] is False

    def test_update_deal_status_can_execute(self):
        p = get_action_policy(ActionType.UPDATE_DEAL_STATUS, confidence=0.9)
        assert p["requires_creator_approval"] is False
        assert p["requires_hitl_review"] is False
        assert p["can_execute"] is True

    def test_draft_brand_deal_low_confidence_requires_hitl(self):
        p = get_action_policy(ActionType.DRAFT_BRAND_DEAL_EMAIL, confidence=0.5)
        assert p["requires_hitl_review"] is True

    def test_draft_brand_deal_high_confidence_ok(self):
        p = get_action_policy(ActionType.DRAFT_BRAND_DEAL_EMAIL, confidence=0.9)
        assert p["requires_hitl_review"] is False
