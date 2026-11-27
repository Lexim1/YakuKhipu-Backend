from datetime import date
from fastapi import APIRouter,Depends
from sqlalchemy.orm import Session
from ..auth.sesion import actor_sunass
from ..core.config import settings
from ..core.db import get_db
from ..modules import finanzas
from ..schemas.comun import Actor

router=APIRouter(prefix='/api/finanzas',tags=['Datos D3'])

@router.get('/resumen')
def resumen(corte:date|None=None,eps_id:str|None=None,actor:Actor=Depends(actor_sunass),db:Session=Depends(get_db)):
    return finanzas.resumen(db,actor,corte or settings.hoy(),eps_id)

@router.get('/eps/{eps_id}')
def ficha(eps_id:str,corte:date|None=None,actor:Actor=Depends(actor_sunass),db:Session=Depends(get_db)):
    return finanzas.ficha_eps(db,actor,eps_id,corte or settings.hoy())
