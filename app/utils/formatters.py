from __future__ import annotations

import json
import re
from collections import OrderedDict
from collections.abc import Mapping
from typing import Any
from xml.etree import ElementTree as ET

import yaml

from app.core.exceptions import UnsupportedFormatError
from app.schemas.export import ConfigReadResponse, ExportDocument, ExportFormat


_FILE_EXTENSIONS: dict[ExportFormat, str] = {
    ExportFormat.json: ".json",
    ExportFormat.yaml: ".yaml",
    ExportFormat.env: ".env",
    ExportFormat.xml: ".xml",
    ExportFormat.properties: ".properties",
}

_MEDIA_TYPES: dict[ExportFormat, str] = {
    ExportFormat.json: "application/json",
    ExportFormat.yaml: "application/x-yaml",
    ExportFormat.env: "text/plain; charset=utf-8",
    ExportFormat.xml: "application/xml",
    ExportFormat.properties: "text/plain; charset=utf-8",
}


def sanitize_filename(filename: str) -> str:
    cleaned = re.sub(r'[<>:\"/\\|?*]+', "_", filename.strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned or "config-export"


def ensure_extension(filename: str, export_format: ExportFormat) -> str:
    extension = _FILE_EXTENSIONS[export_format]
    cleaned = sanitize_filename(filename)
    if cleaned.lower().endswith(extension):
        return cleaned
    base = cleaned.rsplit(".", 1)[0] if "." in cleaned else cleaned
    return f"{base}{extension}"


def _rows_as_mapping(snapshot: ConfigReadResponse) -> OrderedDict[str, str]:
    return OrderedDict((row.key, row.val) for row in snapshot.rows)


def _source_mapping(
    snapshot: ConfigReadResponse,
    resolved_rows: Mapping[str, Any] | None,
) -> OrderedDict[str, Any]:
    if resolved_rows is not None:
        return OrderedDict((str(key), value) for key, value in resolved_rows.items())
    return OrderedDict(_rows_as_mapping(snapshot))


def _flatten_for_env(data: Any, prefix: str = "") -> list[tuple[str, str]]:
    if isinstance(data, Mapping):
        lines: list[tuple[str, str]] = []
        for key, value in data.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            lines.extend(_flatten_for_env(value, child_prefix))
        return lines

    if isinstance(data, list):
        lines: list[tuple[str, str]] = []
        for index, value in enumerate(data):
            child_prefix = f"{prefix}[{index}]" if prefix else f"[{index}]"
            lines.extend(_flatten_for_env(value, child_prefix))
        return lines

    rendered = "" if data is None else str(data)
    return [(prefix, rendered)] if prefix else []


def _append_xml_value(parent: ET.Element, key: str, value: Any) -> None:
    entry = ET.SubElement(parent, "entry")
    entry.set("key", key)
    if isinstance(value, Mapping):
        entry.set("type", "object")
        for child_key, child_value in value.items():
            _append_xml_value(entry, str(child_key), child_value)
        return
    if isinstance(value, list):
        entry.set("type", "array")
        for index, child_value in enumerate(value):
            _append_xml_value(entry, str(index), child_value)
        return
    entry.text = "" if value is None else str(value)


def _render_json(snapshot: ConfigReadResponse, resolved_rows: Mapping[str, Any] | None) -> bytes:
    return json.dumps(_source_mapping(snapshot, resolved_rows), ensure_ascii=False, indent=2).encode("utf-8")


def _render_yaml(snapshot: ConfigReadResponse, resolved_rows: Mapping[str, Any] | None) -> bytes:
    return yaml.safe_dump(dict(_source_mapping(snapshot, resolved_rows)), allow_unicode=True, sort_keys=False).encode("utf-8")


def _render_env(snapshot: ConfigReadResponse, resolved_rows: Mapping[str, Any] | None) -> bytes:
    mapping = _source_mapping(snapshot, resolved_rows)
    lines = [f"{key}={value}" for key, value in _flatten_for_env(mapping)]
    return ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")


def _render_properties(snapshot: ConfigReadResponse, resolved_rows: Mapping[str, Any] | None) -> bytes:
    mapping = _source_mapping(snapshot, resolved_rows)
    lines = [f"{key}={value}" for key, value in _flatten_for_env(mapping)]
    return ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")


def _render_xml(snapshot: ConfigReadResponse, resolved_rows: Mapping[str, Any] | None) -> bytes:
    root = ET.Element("config")
    root.set("config_relation_uuid", snapshot.config_relation_uuid)
    root.set("environment", snapshot.environment)
    root.set("date_created", snapshot.date_created.isoformat())
    for key, value in _source_mapping(snapshot, resolved_rows).items():
        _append_xml_value(root, key, value)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def render_export_document(
    snapshot: ConfigReadResponse,
    export_format: ExportFormat,
    filename: str | None,
    *,
    version_label: str,
    resolved_rows: Mapping[str, Any] | None = None,
) -> ExportDocument:
    if export_format not in _FILE_EXTENSIONS:
        raise UnsupportedFormatError()

    renderers = {
        ExportFormat.json: _render_json,
        ExportFormat.yaml: _render_yaml,
        ExportFormat.env: _render_env,
        ExportFormat.xml: _render_xml,
        ExportFormat.properties: _render_properties,
    }
    base_name = filename or f"config-{snapshot.environment}-{version_label}"
    normalized_filename = ensure_extension(base_name, export_format)
    return ExportDocument(
        filename=normalized_filename,
        media_type=_MEDIA_TYPES[export_format],
        content=renderers[export_format](snapshot, resolved_rows),
    )
