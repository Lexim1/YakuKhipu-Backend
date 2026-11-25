from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base


class Publicacion(Base):
    """Proyección pública de un trámite: solo los campos habilitados para la ciudadanía."""
    __tablename__ = "publicacion"

    id: Mapped[str] = mapped_column(String(60), primary_key=True)     # tacna-medidores-2026
    tramite_id: Mapped[str] = mapped_column(ForeignKey("tramite.id"), unique=True)
    resumen: Mapped[dict] = mapped_column(JSON)                         # DecisionResumen
    ficha: Mapped[dict | None] = mapped_column(JSON)                    # DecisionPublica (sin el resumen)
    publicada: Mapped[bool] = mapped_column(default=True)


class DocumentoRecibido(Base):
    """Documento que llegó por Mesa de Partes y todavía no se incorpora a un expediente."""
    __tablename__ = "documento_recibido"

    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    datos: Mapped[dict] = mapped_column(JSON)
    incorporado_a: Mapped[str | None] = mapped_column(ForeignKey("tramite.id"))


class Alerta(Base):
    __tablename__ = "alerta"

    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    tramite_id: Mapped[str | None] = mapped_column(ForeignKey("tramite.id"))
    datos: Mapped[dict] = mapped_column(JSON)
    atendida: Mapped[bool] = mapped_column(default=False)


class CifraSector(Base):
    __tablename__ = "cifra_sector"

    id: Mapped[int] = mapped_column(primary_key=True)
    datos: Mapped[dict] = mapped_column(JSON)
