from __future__ import annotations

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base


class Documento(Base):
    """Documento del expediente. visibilidad: interna · publica."""
    __tablename__ = "documento"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    tramite_id: Mapped[str] = mapped_column(ForeignKey("tramite.id"), index=True)
    titulo: Mapped[str] = mapped_column(String(200))
    referencia: Mapped[str | None] = mapped_column(String(120))      # Oficio 156-2026-SUNASS-DRE
    visibilidad: Mapped[str] = mapped_column(String(10), default="interna")
    estado_validacion: Mapped[str] = mapped_column(String(20), default="por_validar")
    archivo: Mapped[str | None] = mapped_column(String(300))          # ruta relativa a DOCUMENTOS_DIR
    paginas: Mapped[int | None] = mapped_column(Integer)
    simulado: Mapped[bool] = mapped_column(default=False)


class Fragmento(Base):
    """Texto de una página. Conserva documento y página para citar."""
    __tablename__ = "fragmento"

    id: Mapped[str] = mapped_column(String(140), primary_key=True)
    documento_id: Mapped[str] = mapped_column(ForeignKey("documento.id", ondelete="CASCADE"), index=True)
    tramite_id: Mapped[str] = mapped_column(ForeignKey("tramite.id"), index=True)
    pagina_pdf: Mapped[int | None] = mapped_column(Integer)
    pagina_impresa: Mapped[str | None] = mapped_column(String(20))
    texto: Mapped[str] = mapped_column(Text)
    requiere_ocr: Mapped[bool] = mapped_column(Boolean, default=False)
    metadatos: Mapped[dict | None] = mapped_column(JSON)
