"""Genera un INSERT de cuenta real para la nueva BD; no conecta ni ejecuta SQL."""
import argparse
import getpass
from app.auth.passwords import hash_password
from scripts.generar_sql import literal


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--id',required=True)
    parser.add_argument('--nombre',required=True)
    parser.add_argument('--rol',required=True,choices=['analista_srt','coordinacion_dre','jefatura_dre','eps'])
    parser.add_argument('--eps-id')
    parser.add_argument('--oidc-issuer')
    parser.add_argument('--oidc-subject')
    a=parser.parse_args()
    if (a.rol=='eps')!=bool(a.eps_id):parser.error('Solo EPS requiere --eps-id.')
    if len(a.id)>80:parser.error('El identificador admite hasta 80 caracteres.')
    if bool(a.oidc_issuer) != bool(a.oidc_subject):
        parser.error('Indica ambos datos OIDC: --oidc-issuer y --oidc-subject.')
    digest=None if a.oidc_issuer else hash_password(getpass.getpass('Contraseña real (mínimo 12 caracteres): '))
    values=[a.id,a.nombre,'eps' if a.rol=='eps' else 'sunass',a.eps_id,a.rol,digest]
    crear = 'INSERT INTO usuario(id,nombre_visible,perfil,eps_id,rol_id,password_hash) VALUES (' + ','.join(
        literal(v) for v in values) + ')'
    if a.oidc_issuer:
        print('BEGIN;')
        print(crear + ';')
        enlace = ','.join(literal(v) for v in (a.oidc_issuer, a.oidc_subject, a.id))
        print(f'INSERT INTO seguridad.identidad_oidc(issuer,subject,usuario_id) VALUES ({enlace});')
        print('COMMIT;')
    else:
        print(crear + ' ON CONFLICT(id) DO NOTHING;')


if __name__=='__main__':main()
