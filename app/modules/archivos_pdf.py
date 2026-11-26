"""Acceso privado y cola documental persistente."""
import hashlib
from functools import lru_cache
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from ..core.config import settings
from ..core.errores import DatosInvalidos, ServicioNoDisponible

LIMITE = 20 * 1024 * 1024


@lru_cache(maxsize=1)
def cliente():
    if not all((settings.pdf_endpoint.startswith("https://"), settings.pdf_bucket,
                settings.pdf_access_key, settings.pdf_secret_key)):
        raise ServicioNoDisponible("Configura el bucket privado de documentos.")
    return boto3.client("s3", endpoint_url=settings.pdf_endpoint, region_name=settings.pdf_region,
                        aws_access_key_id=settings.pdf_access_key, aws_secret_access_key=settings.pdf_secret_key,
                        config=Config(connect_timeout=5, read_timeout=30,
                                      s3={"addressing_style": settings.pdf_addressing_style}))


def almacenar(archivo):
    archivo.seek(0)
    if not archivo.read(8).startswith(b"%PDF-"):
        raise DatosInvalidos("El archivo debe ser un PDF válido.")
    archivo.seek(0, 2)
    tamano = archivo.tell()
    if tamano > LIMITE:
        raise HTTPException(413, "El PDF supera el límite de 20 MiB.")
    archivo.seek(0)
    huella = hashlib.file_digest(archivo, "sha256").hexdigest()
    archivo.seek(0)
    clave = f"originales/{uuid4().hex}.pdf"
    try:
        cliente().put_object(Bucket=settings.pdf_bucket, Key=clave, Body=archivo,
                             ContentLength=tamano, ContentType="application/pdf")
    except (BotoCoreError, ClientError):
        raise ServicioNoDisponible("No se pudo almacenar el PDF.") from None
    return {"clave": clave, "sha256": huella, "bytes": tamano}


def estado(db, id_recepcion, *, incluir_texto=False):
    consulta = ("""SELECT estado, error, paginas FROM procesamiento_pdf WHERE recepcion_id=:id"""
                if incluir_texto else
                """SELECT estado, error, jsonb_array_length(paginas) AS paginas
                   FROM procesamiento_pdf WHERE recepcion_id=:id""")
    fila = db.execute(text(consulta), {"id": id_recepcion}).mappings().one_or_none()
    return dict(fila) if fila else None


def original(db, id_documento):
    return db.execute(text("""SELECT clave FROM procesamiento_pdf
        WHERE recepcion_id=:id AND estado='listo'"""), {"id": id_documento}).scalar()


def descargar(clave):
    try:
        objeto = cliente().get_object(Bucket=settings.pdf_bucket, Key=clave)
    except (BotoCoreError, ClientError):
        raise ServicioNoDisponible("El PDF no está disponible en el almacenamiento.") from None
    cuerpo = objeto["Body"]

    def bloques():
        try:
            yield from cuerpo.iter_chunks(chunk_size=128 * 1024)
        finally:
            cuerpo.close()

    return StreamingResponse(bloques(), media_type="application/pdf",
                             headers={"Content-Disposition": 'attachment; filename="documento.pdf"',
                                      "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})
