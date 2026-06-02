from fastapi import FastAPI
import uvicorn

from app.core.config import settings
from app.routers.export import router as export_router


app = FastAPI(title=settings.app_name, version=settings.app_version)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(export_router)


if __name__ == "__main__":
    uvicorn.run("main:app", host=settings.app_host, port=settings.app_port, reload=settings.app_reload)
