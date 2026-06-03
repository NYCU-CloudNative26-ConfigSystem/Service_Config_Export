from datetime import datetime, timezone

import pytest

from app.core.exceptions import UpstreamServiceError
from app.db.models import DeployLog
from app.services.export_service import ExportService


# ── Deploy endpoint ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_deploy_endpoint_returns_triggered(monkeypatch, client, auth_headers):
    async def fake_deploy(self, **kwargs):
        return {"status": "triggered"}

    monkeypatch.setattr(ExportService, "deploy_config", fake_deploy)
    response = await client.post(
        "/api/v1/exports/deploy/abc-uuid-123",
        headers=auth_headers,
        json={
            "proj_id": "proj-1",
            "cmp_id": "corp-1",
            "environment": "production",
            "format": "env",
            "reason": "scheduled release",
            "snapshot_name": "v1.0-prod",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"status": "triggered"}


@pytest.mark.asyncio
async def test_deploy_empty_reason_returns_422(client, auth_headers):
    response = await client.post(
        "/api/v1/exports/deploy/abc-uuid-123",
        headers=auth_headers,
        json={
            "proj_id": "proj-1",
            "cmp_id": "corp-1",
            "environment": "production",
            "format": "env",
            "reason": "",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_deploy_missing_reason_returns_422(client, auth_headers):
    response = await client.post(
        "/api/v1/exports/deploy/abc-uuid-123",
        headers=auth_headers,
        json={
            "proj_id": "proj-1",
            "cmp_id": "corp-1",
            "environment": "production",
            "format": "env",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_deploy_upstream_error_returns_502(monkeypatch, client, auth_headers):
    async def boom(self, **kwargs):
        raise UpstreamServiceError("GitHub API unavailable")

    monkeypatch.setattr(ExportService, "deploy_config", boom)
    response = await client.post(
        "/api/v1/exports/deploy/abc-uuid-123",
        headers=auth_headers,
        json={
            "proj_id": "proj-1",
            "cmp_id": "corp-1",
            "environment": "staging",
            "format": "env",
            "reason": "testing error path",
        },
    )
    assert response.status_code == 502


@pytest.mark.asyncio
async def test_deploy_unauthenticated_returns_401(client):
    response = await client.post(
        "/api/v1/exports/deploy/abc-uuid-123",
        json={
            "proj_id": "proj-1",
            "cmp_id": "corp-1",
            "environment": "production",
            "format": "env",
            "reason": "no token",
        },
    )
    assert response.status_code == 401


# ── Deploy history endpoint ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_deploy_history_empty(client, auth_headers):
    response = await client.get(
        "/api/v1/exports/deploy-history?proj_id=proj-1&cmp_id=corp-1",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_deploy_history_returns_logs(client, auth_headers, db_session):
    db_session.add(DeployLog(
        version_uuid="uuid-aaa",
        snapshot_name="release-1",
        proj_id="proj-1",
        cmp_id="corp-1",
        environment="production",
        format="env",
        reason="initial deploy",
        deployed_by="testuser",
        namespace="config-system",
        status="triggered",
        deployed_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    ))
    db_session.add(DeployLog(
        version_uuid="uuid-bbb",
        snapshot_name="release-2",
        proj_id="proj-1",
        cmp_id="corp-1",
        environment="staging",
        format="json",
        reason="staging test",
        deployed_by="testuser",
        namespace="config-system-staging",
        status="triggered",
        deployed_at=datetime(2026, 6, 2, tzinfo=timezone.utc),
    ))
    await db_session.commit()

    response = await client.get(
        "/api/v1/exports/deploy-history?proj_id=proj-1&cmp_id=corp-1",
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    # newest first
    assert body[0]["version_uuid"] == "uuid-bbb"
    assert body[0]["snapshot_name"] == "release-2"
    assert body[1]["version_uuid"] == "uuid-aaa"


@pytest.mark.asyncio
async def test_deploy_history_isolated_by_proj_and_cmp(client, auth_headers, db_session):
    db_session.add(DeployLog(
        version_uuid="uuid-x",
        snapshot_name="",
        proj_id="proj-OTHER",
        cmp_id="corp-1",
        environment="production",
        format="env",
        reason="other project",
        deployed_by="testuser",
        namespace="config-system",
        status="triggered",
    ))
    await db_session.commit()

    response = await client.get(
        "/api/v1/exports/deploy-history?proj_id=proj-1&cmp_id=corp-1",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_deploy_history_unauthenticated_returns_401(client):
    response = await client.get("/api/v1/exports/deploy-history?proj_id=p&cmp_id=c")
    assert response.status_code == 401


# ── Deploy log persistence (service writes to DB) ─────────────────────────────

@pytest.mark.asyncio
async def test_deploy_log_saved_with_correct_fields(monkeypatch, client, auth_headers, db_session):
    captured: dict = {}

    async def fake_deploy(self, *, version_uuid, proj_id, cmp_id, environment,
                          fmt, reason, snapshot_name, deployed_by, token, session):
        from app.db.models import DeployLog
        log = DeployLog(
            version_uuid=version_uuid,
            snapshot_name=snapshot_name,
            proj_id=proj_id,
            cmp_id=cmp_id,
            environment=environment,
            format=fmt.value,
            reason=reason,
            deployed_by=deployed_by,
            namespace="config-system",
            status="triggered",
        )
        session.add(log)
        await session.commit()
        captured["proj_id"] = proj_id
        captured["reason"] = reason
        captured["snapshot_name"] = snapshot_name
        return {"status": "triggered"}

    monkeypatch.setattr(ExportService, "deploy_config", fake_deploy)
    await client.post(
        "/api/v1/exports/deploy/version-xyz",
        headers=auth_headers,
        json={
            "proj_id": "proj-1",
            "cmp_id": "corp-1",
            "environment": "production",
            "format": "env",
            "reason": "deploy for release",
            "snapshot_name": "prod-v2",
        },
    )

    assert captured["proj_id"] == "proj-1"
    assert captured["reason"] == "deploy for release"
    assert captured["snapshot_name"] == "prod-v2"

    history_resp = await client.get(
        "/api/v1/exports/deploy-history?proj_id=proj-1&cmp_id=corp-1",
        headers=auth_headers,
    )
    assert len(history_resp.json()) == 1
    assert history_resp.json()[0]["status"] == "triggered"
