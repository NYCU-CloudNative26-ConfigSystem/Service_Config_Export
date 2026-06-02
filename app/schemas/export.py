from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ExportFormat(str, Enum):
    json = "json"
    yaml = "yaml"
    env = "env"
    xml = "xml"
    properties = "properties"


class ConfigRow(BaseModel):
    uuid: str
    key: str
    val: str


class ConfigReadResponse(BaseModel):
    config_relation_uuid: str
    date_created: datetime
    environment: str
    rows: list[ConfigRow]
    approval_status: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    rejection_reason: str | None = None
    created_by: str | None = None
    is_latest: bool | None = None
    change_description: str | None = None


class ConfigHistoryItem(BaseModel):
    config_relation_uuid: str
    date_created: datetime
    date_deleted: datetime | None
    created_by: str | None
    entry_count: int
    is_latest: bool
    environment: str
    template_version_uuid: str | None = None
    template_version_number: int | None = None
    approval_status: str
    approved_by: str | None = None
    approved_at: datetime | None = None
    rejection_reason: str | None = None
    change_description: str | None = None


class ExportDownloadRequest(BaseModel):
    proj_id: str = Field(..., description="Project ID")
    cmp_id: str = Field(..., description="Company ID")
    environment: str = Field("production", description="Environment")
    format: ExportFormat = Field(..., description="Output format")
    version_uuid: str | None = Field(None, description="Specific config version UUID; omit for latest")
    filename: str | None = Field(None, description="Custom filename without extension")


class ExportDocument(BaseModel):
    filename: str
    media_type: str
    content: bytes


class ExportPreviewResponse(BaseModel):
    content: str
    format: str
    filename: str
