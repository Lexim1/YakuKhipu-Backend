# Recepción, agente y calidad de datos — 26/11/2026

## Correcciones

- Recepción permite registrar un expediente CPI/UFI/RP a partir de un documento recibido manualmente por Mesa de Partes y derivarlo a un Analista SRT activo. También permite incorporar a uno existente. Se conserva historial y procedencia, con control de permisos, EPS y versión.
- Se corrige la incorporación que confundía el nombre del responsable con una asignación efectiva. El frontend trata correctamente el 204 sin JSON y carga el catálogo completo de EPS y analistas.
- El worker alterna lectura documental y propuestas; una cola de PDF no posterga indefinidamente el análisis. OCR y modelo son operaciones distintas.
- El chat distingue consulta de cartera, análisis documental y extractos de respaldo. El modelo no puede convertir una respuesta sin verificar en una propuesta automática.
- Cinco nuevas reglas detectan ausencia de reporte, retroceso de avance, duplicados, diferencia de saldo y depósito inferior al programado. Las diferencias requieren revisión humana; no se corrigen los datos fuente ni se generan decisiones regulatorias.

## Datos contrastados

La copia PostgreSQL utilizada tiene corte de ejecución 2026-T2. En las EPS visibles para Coordinación se detectaron un retroceso de avance, cinco diferencias de saldo y seis duplicados en cuarentena. Se agruparon 3.164 registros mensuales de depósito inferior al programado en 59 observaciones por EPS/fondo. En ese corte no hubo proyectos activos sin reporte del último trimestre: los proyectos sin ese reporte estaban concluidos. La regla se verifica además con un caso controlado.

Los ejemplos de T3 de la captura no se insertan como datos reales. Antes de cargar un nuevo dataset hay que verificar su fecha, procedencia y diferencias respecto a los registros activos.

## Verificación y límites

Frontend: compilación TypeScript/Vite y lint. Backend: pruebas unitarias y HTTP, más integración PostgreSQL con rollback. Los tres ingresos se prueban mediante HTTP, con 401, 403, 422, 201, asignación y visibilidad documental del analista. Las pruebas de callback OIDC y almacenamiento en la suite usan dobles; no equivalen a un recorrido de navegador con Keycloak y bucket reales.

Resultado de la suite completa: 92 pruebas correctas (86 unitarias/HTTP y seis de integración PostgreSQL). La imagen Docker completa también compiló. Adicionalmente se almacenó un PDF técnico de una página en el bucket real: el worker verificó bytes y SHA256, extrajo el texto mediante Poppler y se eliminó el objeto temporal al terminar. Esta prueba no modifica expedientes de producción ni demuestra OCR de un escaneo real.

Se comprobó la API real del proveedor gratuito: hubo respuestas vacías, límites 429 y modelos sin endpoint disponible para ciertos parámetros. La disponibilidad de /health o una salida con extractos no demuestra que el modelo haya generado una recomendación. Las pruebas del proveedor se registran separadas de la suite automatizada.

El diagnóstico confirmó respuestas HTTP 200 con finish_reason=length, cero caracteres de texto y todo el presupuesto de salida consumido. Con nvidia/nemotron-3.5-super-vl:free y LLM_REASONING_EFFORT=none, UFI y RP produjeron respuestas con citas verificables (tres y cuatro fuentes, respectivamente). En CPI se descartó una respuesta por citas no verificables y se entregaron extractos con advertencia. No se interpreta ese respaldo como una recomendación generada. El esfuerzo de razonamiento es configurable y no se fuerza al cambiar de proveedor/modelo.

Se mantiene el bucket privado existente, sin añadir UploadThing. La carga pasa por la API, limitada en tamaño y concurrencia; la extracción/OCR se ejecuta en el worker. La carga directa navegador→bucket requiere configurar y probar CORS, permisos y confirmación del objeto antes de habilitarla. Este cambio no introduce replicación continua, ni modifica el esquema SQL ni la base de Keycloak.

Un Analista SRT sin asignaciones activas no ve expedientes. La Coordinación debe efectuar asignaciones reales; no se asigna arbitrariamente toda la cartera para ocultar esa situación.
