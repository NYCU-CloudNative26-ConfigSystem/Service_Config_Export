from datetime import datetime, timezone

import pytest

from app.schemas.export import ConfigHistoryItem, ConfigReadResponse, ConfigRow, ExportFormat
from app.services.export_service import ExportService
from app.utils.formatters import render_export_document


@pytest.mark.asyncio
async def test_health_check(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_list_versions_endpoint(monkeypatch, client, auth_headers):
    async def fake_list_versions(self, proj_id: str, cmp_id: str, environment: str, token: str):
        return [
            ConfigHistoryItem(
                config_relation_uuid="uuid-1",
                date_created=datetime.now(tz=timezone.utc),
                date_deleted=None,
                created_by="testuser",
                entry_count=2,
                is_latest=True,
                environment=environment,
                approval_status="approved",
            )
        ]

    monkeypatch.setattr(ExportService, "list_versions", fake_list_versions)
    response = await client.get(
        "/api/v1/exports/versions?proj_id=proj-1&cmp_id=corp-1&environment=production",
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body[0]["config_relation_uuid"] == "uuid-1"
    assert body[0]["is_latest"] is True


@pytest.mark.asyncio
async def test_download_endpoint_returns_attachment(monkeypatch, client, auth_headers):
    async def fake_export_config(self, payload, token: str):
        return render_export_document(
            ConfigReadResponse(
                config_relation_uuid="uuid-1",
                date_created=datetime(2026, 5, 27, tzinfo=timezone.utc),
                environment=payload.environment,
                rows=[ConfigRow(uuid="row-1", key="APP_NAME", val="demo")],
            ),
            payload.format,
            payload.filename,
            version_label="latest",
        )

    monkeypatch.setattr(ExportService, "export_config", fake_export_config)
    response = await client.post(
        "/api/v1/exports/download",
        headers=auth_headers,
        json={
            "proj_id": "proj-1",
            "cmp_id": "corp-1",
            "environment": "production",
            "format": "json",
            "filename": "config-download",
        },
    )
    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'attachment; filename="config-download.json"'
    assert response.json() == {"APP_NAME": "demo"}


def test_render_export_document_formats_filename_and_content():
    snapshot = ConfigReadResponse(
        config_relation_uuid="uuid-1",
        date_created=datetime(2026, 5, 27, tzinfo=timezone.utc),
        environment="production",
        rows=[
            ConfigRow(uuid="row-1", key="APP_NAME", val="demo"),
            ConfigRow(uuid="row-2", key="APP_PORT", val="8080"),
        ],
    )

    document = render_export_document(snapshot, ExportFormat.env, "service export", version_label="latest")
    assert document.filename == "service export.env"
    assert document.media_type == "text/plain; charset=utf-8"
    assert document.content.decode("utf-8") == "APP_NAME=demo\nAPP_PORT=8080\n"
