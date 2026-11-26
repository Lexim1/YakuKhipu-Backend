"""Genera un INSERT de cuenta real para la nueva BD; no conecta ni ejecuta SQL."""
import argparse
from scripts.generar_sql import literal


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--id',required=True)
    parser.add_argument('--nombre',required=True)
    parser.add_argument('--rol',required=True,choices=['analista_srt','coordinacion_dre','jefatura_dre','eps'])
    parser.add_argument('--eps-id')
    parser.add_argument('--oidc-issuer',required=True)
    parser.add_argument('--oidc-subject',required=True)
    a=parser.parse_args()
    if (a.rol=='eps')!=bool(a.eps_id):parser.error('Solo EPS requiere --eps-id.')
    if len(a.id)>80:parser.error('El identificador admite hasta 80 caracteres.')
    values=[a.id,a.nombre,'eps' if a.rol=='eps' else 'sunass',a.eps_id,a.rol]
    crear = 'INSERT INTO usuario(id,nombre_visible,perfil,eps_id,rol_id) VALUES (' + ','.join(
        literal(v) for v in values) + ')'
    print('BEGIN;')
    print(crear + ';')
    enlace = ','.join(literal(v) for v in (a.oidc_issuer, a.oidc_subject, a.id))
    print(f'INSERT INTO seguridad.identidad_oidc(issuer,subject,usuario_id) VALUES ({enlace});')
    print('COMMIT;')


if __name__=='__main__':main()
