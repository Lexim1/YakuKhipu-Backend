from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base


class Tramite(Base):
    """Procedimiento CPI, UFI o RP de una EPS.

    Las columnas guardan lo que el sistema controla (estado, paso, versión, plazos).
    Los bloques de presentación del prototipo (línea de tiempo, comparador, impacto…) van en JSON
    hasta que cada uno tenga su propia tabla.
    """
    __tablename__ = "tramite"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)          # identificador canónico
    procedimiento: Mapped[str] = mapped_column(String(3))                  # CPI · UFI · RP
    eps_id: Mapped[str] = mapped_column(ForeignKey("eps.id"), index=True)
    titulo: Mapped[str] = mapped_column(String(200))
    estado: Mapped[str] = mapped_column(String(30))                        # ver services/tramites.ESTADOS
    paso_actual: Mapped[int] = mapped_column(Integer, default=1)           # índice 1..n del flujograma
    etapa: Mapped[str] = mapped_column(String(120))
    responsable: Mapped[str | None] = mapped_column(String(120))
    fecha_inicio: Mapped[date | None] = mapped_column(Date)                # presentación de la solicitud
    fecha_inicio_etapa: Mapped[date | None] = mapped_column(Date)          # RP mide la etapa activa
    fecha_fin: Mapped[date | None] = mapped_column(Date)                   # resolución, si concluyó
    publicable: Mapped[bool] = mapped_column(default=False)
    simulado: Mapped[bool] = mapped_column(default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)               # control de cambios simultáneos
    huella_fuentes: Mapped[str] = mapped_column(String(32), default="")    # cambia al cargar documentos
    presentacion: Mapped[dict | None] = mapped_column(JSON)                # bloques de la vista SUNASS
    ficha_eps: Mapped[dict | None] = mapped_column(JSON)                   # ficha comprensible de la EPS
    ficha_agente: Mapped[dict | None] = mapped_column(JSON)                # eventos y cifras con su fuente
    actualizado: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                  onupdate=func.now())

    __mapper_args__ = {"version_id_col": version}


class Actuacion(Base):
    """Movimiento del expediente. Se guarda junto con el nuevo estado en una transacción."""
    __tablename__ = "actuacion"
    __table_args__ = (UniqueConstraint("tramite_id", "clave_idempotencia"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tramite_id: Mapped[str] = mapped_column(ForeignKey("tramite.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(40))
    titulo: Mapped[str] = mapped_column(String(200))
    detalle: Mapped[str | None] = mapped_column(Text)
    fecha_acreditada: Mapped[date | None] = mapped_column(Date)            # fecha del documento o del cargo
    fecha_por_validar: Mapped[bool] = mapped_column(default=False)         # no se usa para cómputos
    actor: Mapped[str | None] = mapped_column(String(60))                  # EPS · SRT · Consejo Directivo
    documento_id: Mapped[str | None] = mapped_column(String(120))
    fuente: Mapped[str | None] = mapped_column(String(160))                # fragmento que sustenta el hito
    usuario_id: Mapped[str | None] = mapped_column(ForeignKey("usuario.id"))
    estado_origen: Mapped[str] = mapped_column(String(30))
    estado_destino: Mapped[str] = mapped_column(String(30))
    paso_origen: Mapped[int] = mapped_column(Integer)
    paso_destino: Mapped[int] = mapped_column(Integer)
    verificada: Mapped[bool] = mapped_column(default=True)                 # presentación EPS: SUNASS la verifica
    clave_idempotencia: Mapped[str | None] = mapped_column(String(80))
    peticion_hash: Mapped[str | None] = mapped_column(String(64))
    registrado: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReglaPlazo(Base):
    """Regla de cómputo con su fuente. validada=False → la API responde «pendiente de validación»."""
    __tablename__ = "regla_plazo"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)          # cpi-total
    procedimiento: Mapped[str] = mapped_column(String(3), index=True)
    etapa: Mapped[str | None] = mapped_column(String(60))                  # RP: inicio · evaluacion · …
    evento_inicial: Mapped[str] = mapped_column(String(120))
    dias: Mapped[int] = mapped_column(Integer)
    calendario: Mapped[str] = mapped_column(String(20), default="habiles")
    fuente: Mapped[str] = mapped_column(String(200))
    validada: Mapped[bool] = mapped_column(default=False)
    motivo_pendiente: Mapped[str | None] = mapped_column(Text)
