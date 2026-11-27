"""Verificación de solo lectura sobre una base creada por el usuario con los SQL."""
import os
import pytest


def test_integridad_postgres():
    url=os.environ.get('VERIFY_DATABASE_URL')
    if not url: pytest.skip('Configura VERIFY_DATABASE_URL después de ejecutar los SQL manualmente.')
    import psycopg
    with psycopg.connect(url.replace('postgresql+psycopg://', 'postgresql://', 1),connect_timeout=5) as connection:
        connection.execute('SET TRANSACTION READ ONLY')
        # El lote base contiene 31 documentos/729 fragmentos; D3 y las recepciones
        # posteriores amplían esta base sin invalidar sus relaciones.
        assert connection.execute('SELECT count(*) FROM documento').fetchone()[0]>=31
        assert connection.execute('SELECT count(*) FROM fragmento').fetchone()[0]>=729
        assert connection.execute('SELECT count(*) FROM documento d LEFT JOIN tramite t ON t.id=d.tramite_id WHERE t.id IS NULL').fetchone()[0]==0
        assert connection.execute('SELECT count(*) FROM ejecucion_inversion x LEFT JOIN proyecto_inversion p USING(eps_id,cod_proyecto) WHERE p.cod_proyecto IS NULL').fetchone()[0]==0
