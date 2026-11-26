from __future__ import annotations

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base


class Eps(Base):
    """Empresa prestadora."""
    __tablename__ = "eps"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    region: Mapped[str | None] = mapped_column(String(60))
    tamano: Mapped[str | None] = mapped_column(String(20))           # Pequeña · Mediana · Grande
    simulado: Mapped[bool] = mapped_column(default=False)


class Usuario(Base):
    """Persona que usa el portal. En la demo se identifica por su cargo, nunca por su nombre."""
    __tablename__ = "usuario"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    nombre_visible: Mapped[str] = mapped_column(String(120))        # «Especialista SRT»
    perfil: Mapped[str] = mapped_column(String(10))                  # sunass · eps
    eps_id: Mapped[str | None] = mapped_column(ForeignKey("eps.id"))
    activo: Mapped[bool] = mapped_column(default=True)
    rol_id: Mapped[str] = mapped_column(String(30))
    credenciales_version: Mapped[int] = mapped_column(default=1)
