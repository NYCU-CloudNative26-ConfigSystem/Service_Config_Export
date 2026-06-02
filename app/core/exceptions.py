from fastapi import HTTPException, status


class ExportServiceError(Exception):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Export request could not be processed."

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or self.default_detail
        super().__init__(self.detail)


class InvalidTokenError(ExportServiceError):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Invalid JWT token."


class MissingTokenError(ExportServiceError):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Missing Authorization: Bearer token."


class UpstreamServiceError(ExportServiceError):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "Config service request failed."


class SnapshotNotFoundError(ExportServiceError):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Config snapshot not found."


class UnsupportedFormatError(ExportServiceError):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Unsupported export format."


def to_http_exception(exc: ExportServiceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)
