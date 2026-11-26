"""Mapeos del SQL único. La aplicación no ejecuta DDL."""
from datetime import datetime
from sqlalchemy import String, DateTime, Integer, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from ..core.db import Base

class RolPermiso(Base):
    __tablename__ = 'rol_permiso'
    __table_args__ = {'schema': 'seguridad'}
    rol_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    permiso_id: Mapped[str] = mapped_column(String(60), primary_key=True)

class SesionPersistente(Base):
    __tablename__ = 'sesion'
    __table_args__ = {'schema': 'seguridad'}
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    usuario_id: Mapped[str] = mapped_column(String(80))
    refresh_hash: Mapped[str] = mapped_column(String(64))
    credenciales_version: Mapped[int] = mapped_column(Integer)
    creada: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    vence: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revocada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo_revocacion: Mapped[str | None] = mapped_column(String)

class Asignacion(Base):
    __tablename__ = 'asignacion_tramite'
    id: Mapped[int] = mapped_column(primary_key=True)
    tramite_id: Mapped[str] = mapped_column(String(80))
    usuario_id: Mapped[str] = mapped_column(String(80))
    asignado_por: Mapped[str] = mapped_column(String(80))
    inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fin: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo: Mapped[str | None] = mapped_column(String)
