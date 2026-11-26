"""Worker independiente de la API para extracción y OCR por página."""
import hashlib
import asyncio
import json
import logging
import os
import re
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, sleep

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import text

from .core.config import settings
from .core.db import SesionDB
from .modules.archivos_pdf import cliente

LOG = logging.getLogger(__name__)
MAX_PAGINAS = 80
MAX_TEXTO = 100_000


class PDFInvalido(Exception):
    pass


def ejecutar(args, hasta):
    restante = hasta - monotonic()
    if restante <= 0:
        raise subprocess.TimeoutExpired(args, 0)
    entorno = {k: os.environ[k] for k in ("PATH", "SystemRoot", "TMP", "TEMP") if k in os.environ}
    entorno.update({"LANG": "C", "OMP_THREAD_LIMIT": "1"})
    return subprocess.run(args, capture_output=True, check=True, env=entorno,
                          timeout=min(60, restante)).stdout


def extraer(ruta, carpeta):
    hasta = monotonic() + 12 * 60
    info = ejecutar(["pdfinfo", str(ruta)], hasta).decode(errors="replace")
    paginas = re.search(r"^Pages:\s+(\d+)\s*$", info, re.MULTILINE)
    if not paginas or not 1 <= int(paginas[1]) <= MAX_PAGINAS:
        raise PDFInvalido(f"Se admiten PDFs de 1 a {MAX_PAGINAS} páginas.")
    if re.search(r"^Encrypted:\s+yes", info, re.MULTILINE):
        raise PDFInvalido("El PDF está protegido. Adjunta una copia sin contraseña.")
    resultado = []
    for numero in range(1, int(paginas[1]) + 1):
        seleccion = ["-f", str(numero), "-l", str(numero)]
        texto = ejecutar(["pdftotext", *seleccion, "-enc", "UTF-8", str(ruta), "-"], hasta)
        origen = "texto_pdf"
        if not texto.strip():
            imagen = carpeta / "pagina"
            ejecutar(["pdftoppm", *seleccion, "-scale-to", "2400", "-gray", "-singlefile", "-png",
                      str(ruta), str(imagen)], hasta)
            texto = ejecutar(["tesseract", str(imagen.with_suffix(".png")), "stdout", "-l", "spa"], hasta)
            origen = "ocr"
        salida = texto.decode("utf-8", errors="replace").replace("\x00", "").strip()
        if len(salida) > MAX_TEXTO:
            raise PDFInvalido("Una página supera el límite de texto extraíble.")
        resultado.append({"texto": salida, "origen": origen})
    if not any(p["texto"] for p in resultado):
        raise PDFInvalido("No se pudo reconocer texto en ninguna página.")
    return resultado


def tomar(db):
    db.execute(text("""UPDATE procesamiento_pdf SET estado='fallido', error='Se agotaron los intentos de procesamiento.'
        WHERE estado='procesando' AND intentos>=3 AND tomado < now()-interval '20 minutes'"""))
    fila = db.execute(text("""WITH siguiente AS (
        SELECT recepcion_id FROM procesamiento_pdf
        WHERE intentos<3 AND (estado='pendiente' OR (estado='procesando' AND tomado < now()-interval '20 minutes'))
        ORDER BY creado LIMIT 1 FOR UPDATE SKIP LOCKED
    ) UPDATE procesamiento_pdf p SET estado='procesando', tomado=now(), intentos=intentos+1
        FROM siguiente WHERE p.recepcion_id=siguiente.recepcion_id
        RETURNING p.recepcion_id, p.clave, p.sha256, p.bytes, p.intentos""")).mappings().one_or_none()
    db.commit()
    return fila


def procesar(trabajo):
    objeto = cliente().get_object(Bucket=settings.pdf_bucket, Key=trabajo["clave"])
    cuerpo = objeto["Body"]
    try:
        if objeto["ContentLength"] != trabajo["bytes"]:
            raise PDFInvalido("El PDF almacenado no coincide con el recibido.")
        with TemporaryDirectory() as temporal:
            carpeta = Path(temporal)
            ruta = carpeta / "original.pdf"
            huella = hashlib.sha256()
            restante = trabajo["bytes"]
            hasta = monotonic() + 90
            with ruta.open("wb") as archivo:
                for chunk in cuerpo.iter_chunks(chunk_size=128 * 1024):
                    restante -= len(chunk)
                    if restante < 0 or monotonic() > hasta:
                        raise PDFInvalido("La copia almacenada supera los límites de procesamiento.")
                    huella.update(chunk)
                    archivo.write(chunk)
            if restante or huella.hexdigest() != trabajo["sha256"]:
                raise PDFInvalido("El PDF almacenado no coincide con el recibido.")
            return extraer(ruta, carpeta)
    finally:
        cuerpo.close()


def ciclo():
    with SesionDB() as db:
        trabajo = tomar(db)
    if not trabajo:
        return False
    mensaje = paginas = None
    estado = "listo"
    try:
        paginas = procesar(trabajo)
    except PDFInvalido as exc:
        estado, mensaje = "fallido", str(exc)
    except subprocess.CalledProcessError:
        estado, mensaje = "fallido", "El PDF está protegido, dañado o no se pudo leer."
    except (BotoCoreError, ClientError, OSError, subprocess.TimeoutExpired) as exc:
        LOG.warning("Error de procesamiento de %s: %s", trabajo["recepcion_id"], type(exc).__name__)
        estado = "pendiente" if trabajo["intentos"] < 3 else "fallido"
        mensaje = "No se pudo completar la lectura del PDF."
    with SesionDB.begin() as db:
        db.execute(text("""UPDATE procesamiento_pdf SET estado=:estado, error=:error, paginas=CAST(:paginas AS jsonb)
            WHERE recepcion_id=:id AND intentos=:intento AND estado='procesando'"""),
            {"estado":estado, "error":mensaje, "paginas":json.dumps(paginas) if paginas else None,
             "id":trabajo["recepcion_id"], "intento":trabajo["intentos"]})
    return estado != "pendiente"


def main():
    logging.basicConfig(level=logging.INFO)
    cliente()
    while True:
        try:
            leido = ciclo()
            from .modules import propuestas
            analizado = asyncio.run(propuestas.ciclo())
            if leido or analizado:
                continue
        except Exception as exc:
            LOG.error("El worker no pudo completar el ciclo: %s", type(exc).__name__)
        sleep(5)


if __name__ == "__main__":
    main()
