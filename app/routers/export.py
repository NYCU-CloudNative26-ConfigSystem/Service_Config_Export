import logging

from fastapi import APIRouter, Depends, Response

from app.core.exceptions import ExportServiceError, to_http_exception
from app.routers.deps import CurrentUser, get_current_user
from app.schemas.export import ConfigHistoryItem, ExportDownloadRequest, ExportPreviewResponse
from app.services.export_service import ExportService


router = APIRouter(prefix="/api/v1", tags=["config-export"])
logger = logging.getLogger(__name__)


def _svc() -> ExportService:
    return ExportService()


@router.get(
    "/exports/versions",
    response_model=list[ConfigHistoryItem],
    summary="List exportable config versions",
)
async def list_export_versions(
    proj_id: str,
    cmp_id: str,
    environment: str = "production",
    svc: ExportService = Depends(_svc),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return await svc.list_versions(proj_id, cmp_id, environment, current_user.token)
    except ExportServiceError as exc:
        raise to_http_exception(exc) from exc


@router.post(
    "/exports/preview",
    response_model=ExportPreviewResponse,
    summary="Preview a config snapshot in the selected format without downloading",
)
async def preview_export(
    payload: ExportDownloadRequest,
    svc: ExportService = Depends(_svc),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        document = await svc.export_config(payload, current_user.token)
        return ExportPreviewResponse(
            content=document.content.decode("utf-8"),
            format=payload.format,
            filename=document.filename,
        )
    except ExportServiceError as exc:
        raise to_http_exception(exc) from exc


@router.post(
    "/exports/download",
    summary="Download a config snapshot in the selected format",
)
async def download_export(
    payload: ExportDownloadRequest,
    svc: ExportService = Depends(_svc),
    current_user: CurrentUser = Depends(get_current_user),
):
    logger.info("Received export download request: proj_id=%s cmp_id=%s environment=%s format=%s version_uuid=%s", payload.proj_id, payload.cmp_id, payload.environment, payload.format, payload.version_uuid)
    try:
        document = await svc.export_config(payload, current_user.token)
        return Response(
            content=document.content,
            media_type=document.media_type,
            headers={"Content-Disposition": f'attachment; filename="{document.filename}"'},
        )
    except ExportServiceError as exc:
        logger.warning("Error occurred while exporting config: %s", exc)
        raise to_http_exception(exc) from exc
