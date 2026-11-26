"""Permisos cargados de PostgreSQL; nunca se aceptan del navegador."""
from sqlalchemy import select
from ..core.errores import AccesoDenegado
from ..models.seguridad import RolPermiso

ROLES = {'analista_srt': 'sunass', 'coordinacion_dre': 'sunass', 'jefatura_dre': 'sunass', 'eps': 'eps'}
ACCIONES = {
    'validar_expediente': 'evaluacion.validar', 'confirmar_vinculo': 'evaluacion.validar',
    'avanzar_paso': 'acto_externo.registrar', 'resolver': 'acto_externo.registrar',
    'requerir_informacion': 'requerimiento.registrar', 'requerir_subsanacion': 'requerimiento.registrar',
    'verificar_respuesta': 'respuesta.verificar', 'informar_presentacion': 'eps.respuesta_informar',
}

def cargar(db, rol):
    return list(db.scalars(select(RolPermiso.permiso_id).where(RolPermiso.rol_id == rol)))

def exigir(actor, permiso):
    if permiso not in actor.permisos:
        raise AccesoDenegado('No tienes permiso para esta operación.')
