from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base


class Conversacion(Base):
    """Hilo del asistente. Ligado a su propietario, su ámbito y su caso: no se mezclan perfiles."""
    __tablename__ = "conversacion"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    usuario_id: Mapped[str | None] = mapped_column(ForeignKey("usuario.id"))  # null en Ciudadanía
    ambito: Mapped[str] = mapped_column(String(10))                            # sunass · eps · publico
    eps_id: Mapped[str | None] = mapped_column(String(80))
    visitante_id: Mapped[str | None] = mapped_column(String(36))
    tramite_id: Mapped[str] = mapped_column(ForeignKey("tramite.id"), index=True)
    creada: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Mensaje(Base):
    __tablename__ = "mensaje"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversacion_id: Mapped[str] = mapped_column(ForeignKey("conversacion.id", ondelete="CASCADE"), index=True)
    pregunta: Mapped[str] = mapped_column(Text)
    respuesta: Mapped[str] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(String(20))
    fuentes: Mapped[list | None] = mapped_column(JSON)
    advertencias: Mapped[list | None] = mapped_column(JSON)
    modelo: Mapped[str | None] = mapped_column(String(120))     # registro técnico para evaluar el servicio
    duracion_ms: Mapped[int | None] = mapped_column(Integer)
    desde_cache: Mapped[bool] = mapped_column(default=False)
    creado: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RespuestaCache(Base):
    """Respuestas ya comprobadas. La clave incluye perfil, EPS, trámite y versión de sus fuentes."""
    __tablename__ = "respuesta_cache"

    clave: Mapped[str] = mapped_column(String(64), primary_key=True)
    tramite_id: Mapped[str] = mapped_column(String(80), index=True)
    salida: Mapped[dict] = mapped_column(JSON)
    guardado: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
