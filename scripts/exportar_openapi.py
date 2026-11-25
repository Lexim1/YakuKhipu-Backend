"""Exporta el contrato frontend sin conectar a BD ni llamar a un proveedor IA."""
import json
from pathlib import Path
from app.main import app


def main():
    path=Path(__file__).resolve().parents[1]/'docs'/'openapi.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(app.openapi(),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Contrato exportado: {len(app.openapi()["paths"])} rutas')


if __name__=='__main__': main()
