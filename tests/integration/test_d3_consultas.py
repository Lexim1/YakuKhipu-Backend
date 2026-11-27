import os
from datetime import date
import pytest

def test_d3_finanzas_fuentes_y_ambito_real():
    url=os.environ.get('VERIFY_DATABASE_URL')
    if not url:pytest.skip('Requiere copia QA PostgreSQL')
    from sqlalchemy import create_engine,select,text
    from sqlalchemy.orm import Session
    from app.models import Usuario
    from app.auth.sesion import actor_de
    from app.modules.finanzas import resumen,ficha_eps
    from app.core.errores import NoEncontrado
    engine=create_engine(url)
    with engine.connect() as connection:
        tx=connection.begin();connection.execute(text('SET TRANSACTION READ ONLY'))
        with Session(bind=connection) as db:
            user=db.scalars(select(Usuario).where(Usuario.rol_id=='jefatura_dre',Usuario.activo.is_(True))).first()
            actor=actor_de(user,db);d=resumen(db,actor,date(2026,11,20))
            assert d['total']['programado']>0
            assert any(r['x']=='2026-T3' for r in d['ejecucion_trimestral'])
            assert any(r['x']=='2026-10' for r in d['fondos'])
            assert any('2026T3' in name for name in d['archivos_fuente'])
            assert d['variacion_trimestral_pct'] is None
            with pytest.raises(NoEncontrado):ficha_eps(db,actor,'eps-que-no-existe',date(2026,11,20))
            # El lector técnico no necesita superusuario para las lecturas de finanzas.
            connection.execute(text('SET LOCAL ROLE yakukhipu_final_api'))
            assert resumen(db,actor,date(2026,11,20))['total']==d['total']
        tx.rollback()
    engine.dispose()
