# Demostración UFI desde una solicitud hasta su resolución

Este recorrido se ejecuta en la copia QA con OIDC, PostgreSQL, almacenamiento privado y extracción PDF reales. La inferencia permanece deshabilitada. No altera el expediente original importado ni la producción Railway. La rama requiere el frontend del PR complementario.

## Fuente elegida

Archivo original: `D:\sunass\yakukhipu\mvp\D3_gestion_financiera\datos_sprint\expedientes_ficticios\UFI-2024-0001.pdf`.

- EPS07: EPS Aguas del Valle Alto S.A.
- Solicitud: CARTA N.° 006-2024-EPS07/GG, 10/06/2024, página 2; anexos referenciales en páginas 3–5.
- Motivo: colapso de colector principal. Monto solicitado: S/ 424 142,40.
- Requerimiento: OF-2024-0013, 20/06/2024, página 8.
- Respuesta: CARTA N.° 007-2024-EPS07/GG, 24/06/2024, página 9.
- Informe: INF-2024-0023, 08/07/2024, página 10.
- Memorándum: MEM-2024-0011, 16/07/2024, página 11.
- Resolución: RCD-2024-0011, 25/07/2024, página 12. Autoriza parcialmente S/ 254 485,44.

El material está rotulado como ficticio por sus autores y no tiene validez oficial. Los folios del índice no equivalen al número de páginas reproducidas en el kit resumido.

**Excluir `Solicitud_UFI_SIMULADO` y cualquier solicitud redactada aparte.** `01-Solicitud-y-anexos.pdf` es una extracción de las páginas 2–5 del PDF original, con su contenido conservado. Los demás extractos mantienen las páginas originales indicadas. No subir el expediente completo al principio: revelaría al agente el informe y la resolución antes de incorporarlos en el recorrido.

Los hitos TUPA, evaluación, firmas y elevación a CD tienen registro en `ds10_bitacora_actuaciones.csv`, pero no todos traen un PDF individual en el paquete. Los archivos `04a` a `04d` son transcripciones expresamente rotuladas de esas filas, con ID de actuación y procedencia. No representan documentos originales firmados. Se incorporan únicamente cuando llega su etapa.

Se elige 2024 porque contiene el desenlace. `UFI-2026-0001.pdf` contiene una solicitud de S/ 436 594,67 por rotura de línea de conducción y un informe en evaluación; no incluye una resolución final que permita demostrar un cierre documentado.

## Preparación

1. Iniciar QA en `https://127.0.0.1:5445`. El perfil usa la base `yakukhipu_qa_agente`; el worker PDF debe estar activo. `/health` informa `asistente=deshabilitado`.
2. Utilizar cuatro sesiones separadas de navegador, o cerrar la sesión institucional antes de cambiar de usuario. Cuatro pestañas de un mismo perfil comparten las cookies y no representan cuatro roles independientes.
3. Cuentas locales: `local-jefatura`, `local-coordinacion`, `qa-carga-beto` y `qa-eps-valle-alto`. La última pertenece a EPS07; `local-eps` pertenece a otra EPS y no sirve para ver este caso. Las contraseñas se consultan en el visor privado de cuentas de QA, nunca en Git ni en los PDF.
4. Definir una referencia de ensayo nueva, por ejemplo `DEMO-UFI-001`. Conservar el número original en el título y distinguir la referencia de la recepción de la del expediente importado. El backend devuelve un ID `UFI-MP-...`; anótalo y úsalo en todas las sesiones. Si se repite el ingreso con la misma referencia/EPS/procedimiento, el sistema rechaza el duplicado.
5. En cada carga, seleccionar EPS Aguas del Valle Alto S.A., marcar **Material ficticio de práctica**, introducir la fecha del documento y esperar **PDF listo**. Usar **Actualizar estado** cuando corresponda. La extracción digital/OCR no consume OpenRouter.

## Recorrido por rol

Para incorporar un documento posterior: Recepción → Cargar PDF recibido → esperar listo → Vincular o registrar expediente → elegir el expediente `UFI-MP-...` de esta prueba → Incorporar documento. Conservar la asignación salvo que se quiera efectuar una reasignación explícita.

Para compartir una fuente: Expediente → Documentos incorporados → Revisar acceso EPS → SUNASS y EPS de este expediente → motivo de revisión → Guardar acceso revisado. Los documentos nuevos quedan internos hasta esa revisión. Esta operación no publica para ciudadanía.

Para registrar una actuación: Expediente → Registrar actuación con sustento → seleccionar actuación, documento y fecha acreditada → detalle → Confirmar actuación documentada. Se registra un hecho respaldado; no se emiten firmas oficiales desde el prototipo.

| Paso | Sesión y módulo | Archivo y fecha | Operación y resultado esperado |
|---|---|---|---|
| 1 | Jefatura · Recepción | `01-Solicitud-y-anexos.pdf`, 10/06/2024 | Registrar expediente nuevo, procedimiento UFI, ingreso 10/06/2024. Conservar «Sin asignar; Coordinación lo deriva después». Pulsar **Registrar solicitud**. Queda en Solicitud, sin analista y sin publicar. |
| 2 | Jefatura · Expediente | Solicitud incorporada | Revisar acceso EPS y compartir la solicitud con EPS07. El agente puede localizar su contenido; aún no tiene la resolución en este caso nuevo. |
| 3 | Jefatura · Recepción y Expediente | `02-Proveido-DRE.pdf`, 11/06/2024 | Incorporar y registrar **Pasar a «Deriva a SRT»**. El flujograma marca Solicitud como hecho y Deriva a SRT como actual. |
| 4 | Coordinación · Recepción y Expediente | `03-Proveido-SRT.pdf`, 12/06/2024 | Incorporar. En **Asignar expediente**, revisar carga abierta, elegir QA Beto u otro analista habilitado y justificar. Confirmar. Registrar por separado **Pasar a «Asigna equipo»** con el proveído. |
| 5 | Coordinación · Recepción | `04a-Verificacion-TUPA-DS10.pdf`, 17/06/2024 | Incorporar al mismo expediente. Es respaldo de ACT-001599 del dataset ficticio, no una firma creada. |
| 6 | Analista asignado · Expediente | Respaldo TUPA, 17/06/2024 | Registrar **Pasar a «Verifica requisitos TUPA»**. El analista accede a este caso por su asignación y no puede usar Recepción ni registrar la resolución. |
| 7 | Coordinación · Recepción y Expediente | `05-Oficio-subsanacion.pdf`, 20/06/2024 | Incorporar el oficio y revisar acceso para EPS07. |
| 8 | Analista · Expediente | Oficio, 20/06/2024 | Registrar **Solicitar subsanación**. Introducir los **10 días expresos del PDF** y tres requisitos: costos unitarios, cronograma coherente y acuerdo de Directorio. La EPS pasa a tener una tarea de subsanación. |
| 9 | EPS07 · Mis trámites | Oficio compartido | Abrir el mismo ID. Revisar requisitos y **Leer documento**; abrir el PDF autorizado. El plazo aparece por validar si faltan notificación/calendario, sin inventar un vencimiento. |
| 10 | EPS07 · Preparar respuesta | Referencia CARTA N.° 007-2024-EPS07/GG, 24/06/2024 | Marcar los puntos preparados y pulsar **Ya presenté mi subsanación**. Informar referencia, fecha y cargo de práctica por Mesa de Partes. Queda pendiente de verificación SUNASS. El aviso no equivale a subir ni verificar un PDF. |
| 11 | Coordinación · Recepción y Expediente | `06-Respuesta-EPS.pdf`, 24/06/2024 | Incorporar la copia recibida de la respuesta y compartirla con EPS07. No reutilizar el oficio del requerimiento como respuesta. |
| 12 | Analista · Expediente | Respuesta EPS, 24/06/2024 | Registrar **Verificar la respuesta de la EPS**, seleccionando la carta recién incorporada. La EPS observa que SUNASS verificó su presentación. |
| 13 | Coordinación y Analista | `04b-Evaluacion-DS10.pdf`, 28/06/2024 | Coordinación incorpora el respaldo ACT-001602. El analista registra **Pasar a «Evalúa información»** con esa fecha. |
| 14 | Coordinación y Analista | `07-Informe-SRT.pdf`, 08/07/2024 | Coordinación incorpora el informe. El analista usa **Registrar informe de evaluación**. Queda trazado sin fingir firmas de DRE/OAJ ni resolver el expediente. El informe interno no se comparte por defecto con EPS. |
| 15 | Jefatura · Recepción y Expediente | `04c-Visado-y-firmas-DS10.pdf`, 15/07/2024 | Incorporar el respaldo de ACT-001604/1605/1606. Registrar **Pasar a «Informe único»**. Las fechas de las tres actuaciones se conservan en la transcripción. |
| 16 | Jefatura · Recepción y Expediente | `08-Memorandum-DRE-GG.pdf`, 16/07/2024 | Incorporar y registrar **Pasar a «Memo a GG»**. |
| 17 | Coordinación · Recepción y Expediente | `04d-Elevacion-CD-DS10.pdf`, 19/07/2024 | Incorporar el respaldo ACT-001608. Registrar **Pasar a «Eleva al CD»**. |
| 18 | Jefatura · Recepción y Expediente | `09-Resolucion-CD.pdf`, 25/07/2024 | Incorporar, revisar acceso EPS y registrar **Pasar a «Resolución»**. Luego usar **Registrar la resolución**, resultado **Autorizado parcialmente**, con la misma RCD y fecha. |
| 19 | EPS07 · Seguimiento | RCD-2024-0011 | Ver **Autorizado parcialmente**, sin tarea de subsanación pendiente. Abrir la resolución y comprobar S/ 254 485,44. Los S/ 424 142,40 solicitados no se convierten en monto autorizado. La incorporación/registro no acredita por sí sola la notificación oficial. |

## Módulos que conviene mostrar durante el recorrido

- **Expedientes y flujograma:** etapa actual, siguientes pasos pendientes y documentos incorporados progresivamente. Se conserva el control de versión para evitar sobrescrituras.
- **Asignación:** carga de expedientes abiertos; se excluyen finalizados y asignaciones históricas. Empates y elección humana, con motivo e historial.
- **Línea de tiempo / Actos externos:** constancia de quién registra cada actuación, fecha acreditada y documento. La fecha de incorporación al sistema puede ser posterior a la fecha histórica del documento.
- **Alertas / Plazos:** documentos faltantes y validación pendiente cuando las fuentes no acreditan notificación o calendario. El PDF del oficio expresa diez días; DS10 rotula el hito de subsanación con dos. Conservar esa diferencia, no convertirla en una fecha legal calculada.
- **Ficha 360 / Finanzas:** contexto de EPS07, periodo y procedencia. Los fondos de 2026 no prueban por sí solos el saldo disponible ni la ejecución de esta autorización de 2024. No descontar automáticamente el monto aprobado de otra foto de saldo.
- **Agente:** buscar referencia, colapso de colector o monto; abrir el caso y consultar sus extractos con página. Con inferencia apagada se comprueba recuperación y citas, sin evaluar la interpretación de un modelo real.
- **EPS:** solo sus casos y fuentes revisadas para partes. Probar que un proveído interno o informe no compartido devuelve 404 y que no puede asignar ni resolver.
- **Ciudadanía, opcional al final:** Jefatura usa **Publicar decisión revisada**, selecciona solo la RCD y redacta el resumen público. Esta publicación es distinta del registro de la resolución y no debe revelar solicitud, proveídos o informe interno.

## Validación y límites del pase

Las pruebas de navegador crean un expediente nuevo y completan el recorrido con cuatro sesiones OIDC; no cambian el estado de un caso previamente cerrado para aparentar un flujo. Los documentos se extraen en el worker, se leen desde el bucket privado y se verifica la RCD del mismo expediente. Se prueban los controles de ámbito, versión, documentos y fechas.

El despliegue y la importación en Railway requieren un pase posterior: producción auditada conservaba 31 referencias PDF locales sin archivo disponible en el portal, páginas pendientes de OCR y un solo analista. No afirmar que estos datos quedaron migrados por publicar las ramas QA. El portal y el worker existentes bastan; no se requiere un sexto servicio.
