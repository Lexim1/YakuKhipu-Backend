from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scripts.generar_sql import identity, literal, read_rows, typed, insert
from app.auth.passwords import hash_password, verify_password
from app.modules import plazos, tramites
from app.core.errores import DatosInvalidos
from app.schemas.comun import Actor


def test_ids_no_colisionan_por_origen():
    assert identity('dataset-exp','UFI-2025-0001') != identity('real-exp','UFI-2025-0001')
    assert identity('dataset-exp','UFI-2025-0001') == identity('dataset-exp','UFI-2025-0001')


def test_formato_real_csv_con_extension_xlsx(tmp_path):
    path=tmp_path/'catalogo.xlsx'
    path.write_text('cod_eps,nombre_eps\nEPS01,Nombre fuente\n',encoding='utf-8')
    assert read_rows(path)==[{'cod_eps':'EPS01','nombre_eps':'Nombre fuente'}]


def test_tipos_no_convierten_ausencia_a_cero():
    assert typed('monto_solicitado','') is None
    assert typed('monto_solicitado','0.00') == 0
    assert typed('ubigeo','010101') == '010101'
    assert typed('fecha_inicio','2026-01-01')=='2026-01-01'
    with pytest.raises(ValueError): typed('fecha_inicio','fecha desconocida')


def test_sql_cita_apostrofos_y_no_sustituye_null():
    assert literal("O'Brien") == "'O''Brien'"
    assert literal(None)=='NULL'
    query=insert('tramite',{'id':'real:1','estado':'concluido'},preserve=('estado',))
    assert 'DO NOTHING' in query


def test_password_correcta_incorrecta_y_sal_distinta():
    encoded=hash_password('contraseña-de-prueba')
    assert verify_password('contraseña-de-prueba',encoded)
    assert not verify_password('otra',encoded)
    assert encoded != hash_password('contraseña-de-prueba')


def test_sin_regla_no_declara_vencimiento(monkeypatch):
    db=Mock()
    db.execute.return_value.mappings.return_value.all.return_value=[]
    result=plazos.calcular(db,SimpleNamespace(id='real:1',procedimiento='CPI'),date(2026,11,22))
    assert result['situacion']=='pendiente_de_validacion'
    assert result['fecha_limite'] is None and result['dias_usados'] is None


def test_reloj_suspension_y_calendario_incompleto():
    from app.modules.reloj import contar
    calendar={date(2026,11,d):d not in (21,22) for d in range(17,25)}
    usados,limite=contar(date(2026,11,16),date(2026,11,24),3,calendar,[(date(2026,11,18),date(2026,11,19))])
    assert limite==date(2026,11,23) and usados==4
    with pytest.raises(ValueError): contar(date(2026,11,16),date(2026,11,24),3,{})


def test_documento_ajeno_no_permite_transicion(monkeypatch):
    t=SimpleNamespace(id='real:1',version=1)
    monkeypatch.setattr(tramites.repo,'obtener_tramite',lambda *a,**k:t)
    monkeypatch.setattr(tramites.repo,'obtener_documento',lambda *a:SimpleNamespace(tramite_id='otro'))
    monkeypatch.setattr(tramites,'acciones',lambda *a:[{'tipo':'avanzar_paso','requiere_documento':True}])
    with pytest.raises(DatosInvalidos):
        tramites.registrar(Mock(),Actor(perfil='sunass',usuario_id='operador',permisos=["acto_externo.registrar"]),'real:1',
                          {'tipo':'avanzar_paso','documento_id':'documento-ajeno','fecha_acreditada':date(2026,11,20)},None,date(2026,11,22))


def test_sintaxis_postgresql_sql_generado():
    pglast=pytest.importorskip('pglast')
    root=Path(__file__).resolve().parents[2]/'sql'
    for path in [*root.glob('*.sql'),*(root/'local').glob('*.sql')]:
        content=path.read_text(encoding='utf-8')
        # Solo retirar comandos psql conocidos del encabezado, nunca líneas del texto documental.
        content=content.removeprefix('\\set ON_ERROR_STOP on\n')
        content=content.replace('\\connect yakukhipu_final\n', '', 1)
        for statement in pglast.split(content,with_parser=False):
            pglast.parse_sql(statement)
