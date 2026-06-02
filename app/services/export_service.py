from __future__ import annotations

import logging
from collections.abc import Mapping
from collections import OrderedDict
import json
import re
from urllib.parse import urlencode
from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import InvalidTokenError, UpstreamServiceError
from app.schemas.export import ConfigHistoryItem, ConfigReadResponse, ExportDocument, ExportDownloadRequest
from app.utils.formatters import render_export_document


logger = logging.getLogger(__name__)


class ExportService:
    def __init__(self) -> None:
        self._config_base_url = settings.config_service_url.rstrip("/")
        self._ssot_base_url = settings.ssot_service_url.rstrip("/")
        self._node_id_pattern = re.compile(r"^(VALUE|GROUP):(.+)$")

    async def _request_json(
        self,
        base_url: str,
        path: str,
        token: str,
        service_name: str,
        *,
        allow_not_found: bool = False,
    ) -> object | None:
        url = f"{base_url}{path}"
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                follow_redirects=True,
            )
        if allow_not_found and response.status_code == 404:
            return None
        if response.is_success:
            return response.json()
        raise self._map_upstream_error(response, service_name)

    @staticmethod
    def _map_upstream_error(response: httpx.Response, service_name: str) -> UpstreamServiceError:
        logger.warning("%s upstream error: status=%s body=%s", service_name, response.status_code, response.text)
        detail: str | None = None
        try:
            payload = response.json()
            if isinstance(payload, Mapping):
                detail_value = payload.get("detail")
                if isinstance(detail_value, str) and detail_value:
                    detail = detail_value
                elif detail_value is not None:
                    detail = json.dumps(detail_value, ensure_ascii=False)
        except ValueError:
            pass
        if detail is None:
            detail = response.text.strip() or "Config service request failed."

        if service_name == "SSOT service" and response.status_code in (401, 403):
            return InvalidTokenError(f"{service_name}: {detail}")

        return UpstreamServiceError(f"{service_name}: {detail}")

    async def _resolve_node(self, uuid: str, token: str, cache: dict[str, Mapping[str, Any] | None]) -> Mapping[str, Any] | None:
        if uuid in cache:
            return cache[uuid]
        payload = await self._request_json(
            self._ssot_base_url,
            f"/api/v1/node/{uuid}",
            token,
            "SSOT service",
            allow_not_found=True,
        )
        if isinstance(payload, Mapping):
            cache[uuid] = payload
            return payload
        cache[uuid] = None
        return None

    async def _resolve_name_uuid(self, name_uuid: str, token: str, cache: dict[str, Mapping[str, Any] | None]) -> str:
        node = await self._resolve_node(name_uuid, token, cache)
        if node is None:
            return name_uuid
        if node.get("type") == "name" and isinstance(node.get("name_val"), str):
            return node["name_val"]
        return name_uuid

    async def _resolve_value_ref(self, val_ref: str, token: str, cache: dict[str, Mapping[str, Any] | None]) -> Any:
        match = self._node_id_pattern.match(val_ref)
        if not match:
            return val_ref

        prefix, uuid = match.group(1), match.group(2)
        if prefix == "VALUE":
            node = await self._resolve_node(uuid, token, cache)
            if node is None:
                return None
            if node.get("type") == "value":
                return node.get("val")
            return None

        if prefix == "GROUP":
            return await self._resolve_group_uuid(uuid, token, cache)

        return val_ref

    async def _resolve_group_uuid(self, group_uuid: str, token: str, cache: dict[str, Mapping[str, Any] | None]) -> Any:
        node = await self._resolve_node(group_uuid, token, cache)
        if node is None or node.get("type") != "group":
            return {}

        entries = node.get("entries")
        if not isinstance(entries, list):
            return [] if bool(node.get("isArray")) else {}

        resolved_items: list[tuple[str, Any]] = []
        for raw in entries:
            if not isinstance(raw, Mapping):
                continue
            key_uuid = raw.get("key")
            val_ref = raw.get("val")
            if not isinstance(key_uuid, str) or not isinstance(val_ref, str):
                continue
            key_name = await self._resolve_name_uuid(key_uuid, token, cache)
            value = await self._resolve_value_ref(val_ref, token, cache)
            resolved_items.append((key_name, value))

        if bool(node.get("isArray")):
            indexed_values: list[tuple[int, Any]] = []
            fallback_values: list[Any] = []
            for key_name, value in resolved_items:
                if key_name.isdigit():
                    indexed_values.append((int(key_name), value))
                else:
                    fallback_values.append(value)
            indexed_values.sort(key=lambda item: item[0])
            return [value for _, value in indexed_values] + fallback_values

        result: OrderedDict[str, Any] = OrderedDict()
        for key_name, value in resolved_items:
            result[key_name] = value
        return result

    async def _resolve_snapshot_rows(self, snapshot: ConfigReadResponse, token: str) -> OrderedDict[str, Any]:
        cache: dict[str, Mapping[str, Any] | None] = {}
        resolved: OrderedDict[str, Any] = OrderedDict()
        for row in snapshot.rows:
            key_name = await self._resolve_name_uuid(row.key, token, cache)
            value = await self._resolve_value_ref(row.val, token, cache)
            resolved[key_name] = value
        return resolved

    async def list_versions(self, proj_id: str, cmp_id: str, environment: str, token: str) -> list[ConfigHistoryItem]:
        logger.info("Fetching config history for proj_id=%s cmp_id=%s environment=%s", proj_id, cmp_id, environment)
        query = urlencode({"proj_id": proj_id, "cmp_id": cmp_id, "environment": environment})
        payload = await self._request_json(self._config_base_url, f"/api/v1/config/history?{query}", token, "Config service")
        if not isinstance(payload, list):
            raise UpstreamServiceError()
        return [ConfigHistoryItem.model_validate(item) for item in payload]

    async def _fetch_snapshot_latest(self, proj_id: str, cmp_id: str, environment: str, token: str) -> ConfigReadResponse:
        logger.info("Fetching latest config for proj_id=%s cmp_id=%s environment=%s", proj_id, cmp_id, environment)
        query = urlencode({"proj_id": proj_id, "cmp_id": cmp_id, "environment": environment})
        payload = await self._request_json(self._config_base_url, f"/api/v1/config/?{query}", token, "Config service")
        if not isinstance(payload, Mapping):
            raise UpstreamServiceError()
        return ConfigReadResponse.model_validate(payload)

    async def _fetch_snapshot_by_uuid(self, config_uuid: str, token: str) -> ConfigReadResponse:
        payload = await self._request_json(self._config_base_url, f"/api/v1/config/{config_uuid}", token, "Config service")
        if not isinstance(payload, Mapping):
            raise UpstreamServiceError("Config service: snapshot payload is invalid")
        return ConfigReadResponse.model_validate(payload)

    async def export_config(self, payload: ExportDownloadRequest, token: str) -> ExportDocument:
        if payload.version_uuid:
            snapshot = await self._fetch_snapshot_by_uuid(payload.version_uuid, token)
            version_label = payload.version_uuid[:8]
        else:
            snapshot = await self._fetch_snapshot_latest(payload.proj_id, payload.cmp_id, payload.environment, token)
            version_label = "latest"
        resolved_rows = await self._resolve_snapshot_rows(snapshot, token)
        return render_export_document(snapshot, payload.format, payload.filename, version_label=version_label, resolved_rows=resolved_rows)
