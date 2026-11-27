"""Abrir el documento de una cita: el PDF si está en la carpeta local, o su texto por página."""
from __future__ import annotations

from pathlib import Path
import zipfile

from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..models import Documento, Fragmento
from ..repositories import tramites as repo
from ..schemas.comun import Actor
from ..core.errores import NoEncontrado,ServicioNoDisponible


def pdf_disponible(doc):
    if doc.archivo and doc.archivo.startswith('bucket:fuentes/'):
        return bool(settings.pdf_bucket)
    if not doc.archivo or not settings.documentos_dir: return False
    root=Path(settings.documentos_dir).resolve()
    archive,separator,member=doc.archivo.partition('::')
    path=(root/archive).resolve()
    if root not in path.parents or not path.is_file(): return False
    if not separator: return True
    try:
        with zipfile.ZipFile(path) as z: return member in z.namelist()
    except (OSError,zipfile.BadZipFile): return False


def contenido(db: Session, actor: Actor, documento_id: str, pagina: int | None, formato: str):
    doc = repo.obtener_documento(db, actor, documento_id)
    if pagina and doc.paginas and pagina>doc.paginas:
        raise NoEncontrado('La página indicada no existe en el documento.')
    clave = None
    if doc.archivo and doc.archivo.startswith('bucket:fuentes/'):
        from .archivos_pdf import descargar
        clave=doc.archivo.removeprefix('bucket:')
        if formato=='pdf':return descargar(clave)
    if doc.archivo == "bucket:original":
        from .archivos_pdf import descargar, original
        clave = original(db, doc.id)
        if formato == "pdf" and clave:
            return descargar(clave)
    if formato == "pdf" and doc.archivo and '::' in doc.archivo and settings.documentos_dir:
        archive, member = doc.archivo.split('::',1)
        root = Path(settings.documentos_dir).resolve()
        ruta = (root/archive).resolve()
        if root in ruta.parents and ruta.is_file():
            try:
                with zipfile.ZipFile(ruta) as z:
                    if member in z.namelist():
                        return Response(z.read(member), media_type='application/pdf',headers={'X-Content-Type-Options':'nosniff'})
            except (OSError,zipfile.BadZipFile,RuntimeError):
                raise ServicioNoDisponible('El archivo del documento no está disponible.')
    if formato == "pdf" and doc.archivo and settings.documentos_dir:
        ruta = (Path(settings.documentos_dir) / doc.archivo).resolve()
        if ruta.is_file() and Path(settings.documentos_dir).resolve() in ruta.parents:
            return FileResponse(ruta, media_type="application/pdf", filename=ruta.name,
                                content_disposition_type="inline")
    if formato=='pdf':
        raise NoEncontrado('No hay un PDF disponible para este documento. Consulta formato=texto.')
    consulta = select(Fragmento).where(Fragmento.documento_id == doc.id).order_by(Fragmento.pagina_pdf)
    if pagina:
        consulta = consulta.where(Fragmento.pagina_pdf == pagina)
    paginas = [{"pagina_pdf": f.pagina_pdf, "pagina_impresa": f.pagina_impresa, "texto": f.texto,
                "requiere_ocr": f.requiere_ocr} for f in db.scalars(consulta)]
    if pagina and not paginas:
        raise NoEncontrado('No hay texto registrado para esa página.')
    return {"id": doc.id, "titulo": doc.titulo, "referencia": doc.referencia, "visibilidad": doc.visibilidad,
            "estado_validacion": doc.estado_validacion, "simulado": doc.simulado,
            "pdf_disponible": bool(clave) or pdf_disponible(doc), "paginas": paginas}


def enlace(doc_id: str, pagina: int | None, publico: bool) -> str:
    base = "/api/publico/documentos" if publico else "/api/documentos"
    return f"{base}/{doc_id}/contenido" + (f"?pagina={pagina}" if pagina else "")


def titulos(db: Session, ids: set[str]) -> dict[str, Documento]:
    if not ids:
        return {}
    return {d.id: d for d in db.scalars(select(Documento).where(Documento.id.in_(ids)))}
