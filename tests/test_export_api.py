from datetime import datetime, timezone

import pytest

from app.core.exceptions import UpstreamServiceError
from app.schemas.export import ConfigHistoryItem, ConfigReadResponse, ConfigRow, ExportFormat
from app.services.export_service import ExportService
from app.utils.formatters import render_export_document, sanitize_filename, ensure_extension


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


# ── Auth guard ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unauthenticated_request_returns_401(client):
    response = await client.get("/api/v1/exports/versions?proj_id=p&cmp_id=c&environment=production")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_invalid_token_returns_401(client):
    response = await client.get(
        "/api/v1/exports/versions?proj_id=p&cmp_id=c&environment=production",
        headers={"Authorization": "Bearer not-a-valid-jwt"},
    )
    assert response.status_code == 401


# ── Preview endpoint ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_preview_endpoint_returns_text(monkeypatch, client, auth_headers):
    async def fake_export_config(self, payload, token: str):
        return render_export_document(
            ConfigReadResponse(
                config_relation_uuid="uuid-1",
                date_created=datetime(2026, 1, 1, tzinfo=timezone.utc),
                environment=payload.environment,
                rows=[ConfigRow(uuid="r1", key="KEY", val="value")],
            ),
            payload.format,
            payload.filename,
            version_label="latest",
        )

    monkeypatch.setattr(ExportService, "export_config", fake_export_config)
    response = await client.post(
        "/api/v1/exports/preview",
        headers=auth_headers,
        json={"proj_id": "p", "cmp_id": "c", "environment": "production", "format": "env"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["format"] == "env"
    assert "KEY=value" in body["content"]
    assert body["filename"].endswith(".env")


@pytest.mark.asyncio
async def test_preview_upstream_error_returns_502(monkeypatch, client, auth_headers):
    async def boom(self, payload, token):
        raise UpstreamServiceError("Config service down")

    monkeypatch.setattr(ExportService, "export_config", boom)
    response = await client.post(
        "/api/v1/exports/preview",
        headers=auth_headers,
        json={"proj_id": "p", "cmp_id": "c", "environment": "production", "format": "json"},
    )
    assert response.status_code == 502


# ── Formatter: remaining format coverage ─────────────────────────────────────

def _make_snapshot(rows: list[tuple[str, str]]) -> ConfigReadResponse:
    return ConfigReadResponse(
        config_relation_uuid="uuid-1",
        date_created=datetime(2026, 1, 1, tzinfo=timezone.utc),
        environment="production",
        rows=[ConfigRow(uuid=f"r{i}", key=k, val=v) for i, (k, v) in enumerate(rows)],
    )


def test_render_yaml_format():
    doc = render_export_document(
        _make_snapshot([("HOST", "localhost"), ("PORT", "5432")]),
        ExportFormat.yaml,
        None,
        version_label="v1",
    )
    assert doc.filename.endswith(".yaml")
    assert doc.media_type == "application/x-yaml"
    content = doc.content.decode("utf-8")
    assert "HOST: localhost" in content
    assert "PORT: '5432'" in content


def test_render_xml_format():
    doc = render_export_document(
        _make_snapshot([("DB", "postgres")]),
        ExportFormat.xml,
        "my-config",
        version_label="v1",
    )
    assert doc.filename == "my-config.xml"
    assert doc.media_type == "application/xml"
    assert b"<entry key=\"DB\">postgres</entry>" in doc.content


def test_render_properties_format():
    doc = render_export_document(
        _make_snapshot([("app.name", "svc"), ("app.port", "8080")]),
        ExportFormat.properties,
        None,
        version_label="v1",
    )
    assert doc.filename.endswith(".properties")
    lines = doc.content.decode("utf-8").splitlines()
    assert "app.name=svc" in lines
    assert "app.port=8080" in lines


def test_render_auto_filename_when_none():
    doc = render_export_document(
        _make_snapshot([("X", "1")]),
        ExportFormat.json,
        None,
        version_label="abc123",
    )
    assert doc.filename == "config-production-abc123.json"


def test_sanitize_filename_strips_special_chars():
    assert sanitize_filename('my:file<name>') == "my_file_name_"
    assert sanitize_filename("  ") == "config-export"


def test_ensure_extension_does_not_double_extend():
    assert ensure_extension("output.env", ExportFormat.env) == "output.env"
    assert ensure_extension("output", ExportFormat.env) == "output.env"
