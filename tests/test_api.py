from fastapi.testclient import TestClient

from app.database import reset_db
from app.main import app


def _register(client: TestClient, email: str, company_name: str = "Pilot Importer"):
    response = client.post(
        "/v1/auth/register",
        json={
            "company_name": company_name,
            "industry": "Electronics and Semiconductors",
            "country": "India",
            "preferences": {"objective": "cost-balanced"},
            "full_name": "Ops Admin",
            "email": email,
            "password": "StrongPass123",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_secure_happy_path_with_admin_routes():
    reset_db()

    with TestClient(app) as client:
        auth = _register(client, "admin@pilot.example")
        token = auth["access_token"]
        client_id = auth["client"]["id"]
        headers = {"Authorization": f"Bearer {token}"}

        me = client.get("/v1/auth/me", headers=headers)
        assert me.status_code == 200
        assert me.json()["client"]["id"] == client_id

        supply_map_resp = client.post(
            f"/v1/clients/{client_id}/supply-map",
            headers=headers,
            json={
                "suppliers": [
                    {
                        "name": "Supplier A",
                        "country": "China",
                        "region": "South China",
                        "commodity": "semiconductors",
                        "criticality": 0.9,
                        "substitution_score": 0.3,
                        "lead_time_sensitivity": 0.8,
                        "inventory_buffer_days": 8,
                    }
                ],
                "lanes": [
                    {
                        "origin": "Shanghai",
                        "destination": "Nhava Sheva",
                        "mode": "sea",
                        "importance": 0.8,
                        "chokepoint": "Strait of Malacca",
                    }
                ],
                "sku_groups": [{"name": "Power IC", "category": "semiconductor", "margin_sensitivity": 0.8}],
            },
        )
        assert supply_map_resp.status_code == 201
        assert supply_map_resp.json()["suppliers_added"] == 1
        supply_map_read = client.get(f"/v1/clients/{client_id}/supply-map", headers=headers)
        assert supply_map_read.status_code == 200
        assert len(supply_map_read.json()["suppliers"]) == 1

        user_create = client.post(
            "/v1/users",
            headers=headers,
            json={
                "full_name": "Analyst One",
                "email": "analyst@pilot.example",
                "role": "analyst",
                "password": "StrongPass123",
            },
        )
        assert user_create.status_code == 201
        analyst_id = user_create.json()["id"]

        user_update = client.patch(
            f"/v1/users/{analyst_id}",
            headers=headers,
            json={"role": "viewer", "is_active": True},
        )
        assert user_update.status_code == 200
        assert user_update.json()["role"] == "viewer"

        users = client.get("/v1/users", headers=headers)
        assert users.status_code == 200
        assert len(users.json()) == 2

        sub = client.post(
            "/v1/alerts/subscriptions",
            headers=headers,
            json={
                "channel": "dashboard",
                "target": "control-tower",
                "min_severity": 0.5,
            },
        )
        assert sub.status_code == 201
        subscription_id = sub.json()["id"]
        sub_list = client.get("/v1/alerts/subscriptions", headers=headers)
        assert sub_list.status_code == 200
        assert len(sub_list.json()) == 1
        sub_update = client.patch(
            f"/v1/alerts/subscriptions/{subscription_id}",
            headers=headers,
            json={"active": False},
        )
        assert sub_update.status_code == 200
        assert sub_update.json()["active"] is False
        sub_delete = client.delete(f"/v1/alerts/subscriptions/{subscription_id}", headers=headers)
        assert sub_delete.status_code == 204

        summary = client.get("/v1/dashboard/summary", headers=headers)
        assert summary.status_code == 200
        assert summary.json()["client_name"] == "Pilot Importer"

        audit = client.get("/v1/audit-logs", headers=headers)
        assert audit.status_code == 200
        actions = {item["action"] for item in audit.json()}
        assert "user.create" in actions
        assert "supply_map.upsert" in actions

        overview = client.get("/v1/ops/overview", headers=headers)
        assert overview.status_code == 200
        assert overview.json()["active_users"] == 2

        metrics = client.get("/v1/ops/metrics", headers=headers)
        assert metrics.status_code == 200
        assert "run_count_24h" in metrics.json()

        csv_import = client.post(
            f"/v1/clients/{client_id}/supply-map/import-csv",
            headers=headers,
            json={
                "suppliers_csv": "name,country,region,commodity,criticality,substitution_score,lead_time_sensitivity,inventory_buffer_days\nSupplier A,China,South China,semiconductors,0.95,0.2,0.9,7\n",
                "lanes_csv": "origin,destination,mode,chokepoint,importance\nShanghai,Nhava Sheva,sea,Strait of Malacca,0.9\n",
                "sku_groups_csv": "name,category,monthly_volume,margin_sensitivity\nPower IC,semiconductor,12000,0.85\n",
            },
        )
        assert csv_import.status_code == 201
        assert csv_import.json()["suppliers_updated"] == 1

        events = client.get("/v1/events", headers=headers)
        assert events.status_code == 200
        if events.json():
            event_id = events.json()[0]["id"]
            playbook = client.post(
                f"/v1/clients/{client_id}/playbooks/generate",
                headers=headers,
                json={"event_id": event_id},
            )
            assert playbook.status_code == 200
            playbook_id = playbook.json()["id"]
            approvals = client.get(f"/v1/playbooks/{playbook_id}/approvals", headers=headers)
            assert approvals.status_code == 200
            assert len(approvals.json()) >= 1
            approval_id = approvals.json()[0]["id"]
            approval_update = client.patch(
                f"/v1/playbooks/{playbook_id}/approvals/{approval_id}",
                headers=headers,
                json={"status": "approved", "decision_note": "Approved for execution"},
            )
            assert approval_update.status_code == 200
            assert approval_update.json()["status"] == "approved"

            comment = client.post(
                f"/v1/playbooks/{playbook_id}/comments",
                headers=headers,
                json={"comment": "Escalated to lane-planning team for immediate reroute review."},
            )
            assert comment.status_code == 201

            outcome = client.post(
                f"/v1/clients/{client_id}/events/{event_id}/outcome",
                headers=headers,
                json={
                    "playbook_id": playbook_id,
                    "status": "monitoring",
                    "summary": "Reroute to alternate port in progress.",
                    "actions_taken": ["Booked alternate lane", "Updated customer ETA bands"],
                    "eta_recovery_hours": 48,
                },
            )
            assert outcome.status_code == 201
            assert outcome.json()["status"] == "monitoring"

            outcome_read = client.get(
                f"/v1/clients/{client_id}/events/{event_id}/outcome",
                headers=headers,
            )
            assert outcome_read.status_code == 200
            assert outcome_read.json()["status"] == "monitoring"


def test_cross_tenant_access_is_blocked():
    reset_db()

    with TestClient(app) as client:
        auth_a = _register(client, "admin-a@pilot.example", company_name="Alpha")
        auth_b = _register(client, "admin-b@pilot.example", company_name="Beta")

        headers_a = {"Authorization": f"Bearer {auth_a['access_token']}"}
        client_b_id = auth_b["client"]["id"]

        response = client.post(
            f"/v1/clients/{client_b_id}/supply-map",
            headers=headers_a,
            json={"suppliers": [], "lanes": [], "sku_groups": []},
        )
        assert response.status_code == 403


def test_webhook_ssrf_guard_and_supply_map_idempotency():
    reset_db()
    with TestClient(app) as client:
        auth = _register(client, "admin-idempotency@pilot.example")
        token = auth["access_token"]
        client_id = auth["client"]["id"]
        headers = {"Authorization": f"Bearer {token}"}

        payload = {
            "suppliers": [
                {
                    "name": "Supplier A",
                    "country": "China",
                    "region": "South China",
                    "commodity": "semiconductors",
                    "criticality": 0.9,
                }
            ],
            "lanes": [{"origin": "Shanghai", "destination": "Nhava Sheva", "mode": "sea", "importance": 0.8}],
            "sku_groups": [{"name": "Power IC", "category": "semiconductor", "margin_sensitivity": 0.8}],
        }
        first = client.post(f"/v1/clients/{client_id}/supply-map", headers=headers, json=payload)
        second = client.post(f"/v1/clients/{client_id}/supply-map", headers=headers, json=payload)
        assert first.status_code == 201
        assert second.status_code == 201
        assert first.json()["suppliers_added"] == 1
        assert second.json()["suppliers_updated"] == 1

        ssrf = client.post(
            "/v1/webhooks/test",
            headers=headers,
            json={"url": "http://127.0.0.1/internal", "payload": {"ping": True}},
        )
        assert ssrf.status_code == 422
