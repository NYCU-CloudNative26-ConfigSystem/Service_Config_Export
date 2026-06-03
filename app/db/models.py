from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DeployLog(Base):
    __tablename__ = "deploy_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    version_uuid: Mapped[str] = mapped_column(String(64))
    snapshot_name: Mapped[str] = mapped_column(String(256), default="", server_default="")
    proj_id: Mapped[str] = mapped_column(String(64))
    cmp_id: Mapped[str] = mapped_column(String(64))
    environment: Mapped[str] = mapped_column(String(64))
    format: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(Text)
    deployed_by: Mapped[str] = mapped_column(String(128))
    namespace: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32))
    deployed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
