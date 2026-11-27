# Kits por solicitud y procedimiento

El generador conserva el contenido de los PDF entregados, sus páginas de origen y la procedencia de DS02, DS10 y DS11. No conecta con Railway, no crea expedientes, no ejecuta IA y no importa estados históricos a las solicitudes nuevas.

```powershell
python -m pip install -r scripts/requirements-kits.txt
python -m scripts.generar_kits_demo `
  --datasets 'D:\sunass\yakukhipu\mvp\D3_gestion_financiera\datos_sprint' `
  --actualizacion 'D:\sunass\yakukhipu\mvp\D3_gestion_financiera\datos_sprint\datos_para_demostracion\d3_actualizacion_al_2026-11-20' `
  --salida 'RUTA-DE-SALIDA\kits' --transcribir-hitos --portal-origin 'https://localhost:5443'
```

Se genera una carpeta por cada expediente del dataset actualizado: 501 fichas, agrupadas en CPI, UFI, RP, RPI, IPM y VIN. Los flujos operativos del portal son CPI, UFI y RP; los otros tres grupos se documentan para consulta financiera y no se presentan como flujos operativos implementados.

Hay 15 expedientes con PDF entregado, que contienen 130 documentos identificados. Nueve tienen una solicitud inicial materialmente disponible. RP-2026-0002 comienza con un informe de fecha incoherente y no incluye la solicitud: el kit lo señala. En 486 expedientes solo se entregaron registros e índices; sus fichas no fabrican PDF para llenar ese vacío. `Solicitud_UFI_SIMULADO` queda excluido.

Cada carpeta contiene `00-LEEME.md`, manifiesto, actuaciones e índice documental. Cuando hay originales, contiene los documentos separados y, si existe, `01-Solicitud-y-anexos.pdf`. Los hitos sin PDF propio pueden tener una transcripción rotulada DS10; no se genera con ella una solicitud o resolución. La página de continuación de la conclusión de INF-2024-0003 (RP-2024-0001, página 23) se conserva con su informe, sin adjuntar la portada ni otro documento.

El índice general enlaza los kits con PDF y el catálogo CSV incluye todas las solicitudes. Los ZIP por procedimiento y el ZIP completo permiten transportarlos. No incluyen credenciales. La asignación requiere una cuenta activa y la EPS debe corresponder a la del expediente.

## Recorrido nuevo e históricos

Subir un PDF por Recepción almacena el archivo y extrae su texto. Registrar una solicitud nueva la inicia en Solicitud/Inicio; Jefatura, Coordinación, analista y EPS avanzan mediante actuaciones confirmadas con evidencia. El informe y el cierre se incorporan cuando llegan sus pasos.

Importar históricos es otra operación: conserva el estado declarado en sus fuentes, no equivale al ingreso manual. Este generador no la realiza. Al corte existen 474 registros concluidos, 26 en trámite y uno archivado; esos estados son metadatos de las fuentes, no órdenes para concluir nuevas solicitudes.

CPI-2026-0002 termina con el oficio OF-2026-0017 de archivo por no subsanar. Se registra mediante **Cerrar y archivar con documento**, con permiso de Jefatura/Coordinación, documento compartido para EPS, fecha y motivo. No se fuerza una autorización; las etapas posteriores se muestran como no realizadas.

Los PDF del kit son compactos y respetan los límites de carga del portal. Los 31 originales reales de la base están fuera de estos kits ficticios: algunos superan las 80 páginas admitidas por el procesamiento manual. Su eventual migración privada requiere un pase de datos separado.
