"""Primera llamada al modelo con un texto FICTICIO (guía del backend). Confirma URL, clave y modelo.

Uso (desde backend/):  python -m scripts.probar_modelo
Una respuesta aceptable dice que hay una autorización y que falta información sobre la instalación.
"""
import asyncio
import sys

from app.agent import llm

MENSAJES = [
    {"role": "system", "content": "Explica solo el dato recibido. Distingue autorizado de ejecutado."},
    {"role": "user", "content": "Ejemplo ficticio: se autorizaron 100 medidores. No existe reporte de instalacion. "
                                "Que sabemos?"},
]


async def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        texto, modelo = await llm.completar(MENSAJES, max_tokens=300)
        print(f"[{modelo}] {texto}")
    except llm.ModeloNoDisponible as e:
        print(f"No se obtuvo una respuesta útil. Revisar proveedor y cuota. ({e})")


if __name__ == "__main__":
    asyncio.run(main())
