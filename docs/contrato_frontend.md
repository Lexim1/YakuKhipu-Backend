# Contrato HTTP vigente

La fuente exacta de rutas, entradas y salidas es [openapi.json](openapi.json), generado con python -m scripts.exportar_openapi desde backend.

## Sesión

GET /api/auth/login inicia el ingreso OIDC con Keycloak. El callback abre la sesión persistente. GET /api/sesion devuelve usuario_id, nombre, perfil (sunass/eps), rol_id, permisos, eps_id y eps. DELETE /api/sesion revoca la sesión y devuelve 204. Usar credentials: include en el navegador. La cookie HttpOnly firmada vence en ocho horas; no hay ingreso con contraseña local.

GET /health incluye `ingreso: "oidc"` y `carga_pdf`. El portal enlaza a GET /api/auth/login; Keycloak vuelve a /api/auth/callback, que abre la sesión y redirige a /sunass/expedientes o /eps/tramites (o a /?acceso=fallido). DELETE /api/sesion puede devolver la cabecera X-Logout-URL para cerrar también la sesión en Keycloak. `carga_pdf: "habilitada"` indica que hay bucket para POST /api/recepcion/pdf. El portal y la API comparten origen mediante un proxy de /api.

El servidor consulta roles y permisos de PostgreSQL. No acepta que el cliente elija un rol o EPS como autoridad. Un 401 pide nueva sesión, 403 deniega una facultad, 404 oculta también recursos fuera del ámbito, 409 indica conflicto de versión y 422 entrada inválida. Los errores tienen detail y codigo; 503 indica dependencia no disponible.

## Ámbitos y operaciones

- Analista SRT: expedientes asignados activos, trazabilidad, validación técnica, requerimientos y verificación de respuestas según permisos.
- Coordinación DRE: cartera CPI/UFI/RP, recepción, asignación y registro de actos externos según permisos; sin validación técnica.
- Jefatura DRE: cartera y facultades asignadas en BD.
- EPS: expedientes propios, documentos de partes/públicos e informar presentaciones externas.
- Ciudadanía: solo publicaciones y documentos habilitados, sin login institucional.

GET /api/tramites/{id}/acciones refleja permisos y estado. Las escrituras exigen la versión observada y la evidencia requerida. Resolver registra una resolución externa acreditada; no firma ni aprueba un acto regulatorio.

POST /api/tramites/{id}/asignaciones recibe usuario_id (Analista activo), version y motivo. Requiere asignacion.gestionar; cierra la asignación previa y conserva el historial.

El agente institucional POST /api/agente/chat usa la misma sesión, permiso agente.consultar y ámbito del expediente. El ciudadano POST /api/publico/asistente/chat usa una cookie de visitante y publicaciones. Nunca pasar perfil/rol como decisión de autorización. La propiedad de conversaciones y el acceso se comprueban antes de recuperar memoria y fuentes.

Los valores sin evidencia permanecen null; no convertirlos a cero ni calcular plazos legales en el navegador. Solicitado, autorizado y ejecutado son conceptos distintos.

El frontend publicado se integra mediante el commit fijado en Dockerfile; actualizar ese commit y verificar el despliegue cuando se aprueba una nueva versión del frontend.

## Recepción manual y derivación

No existe conexión automática a Mesa de Partes. Coordinación o Jefatura registra el PDF recibido externamente con referencia, fecha y EPS. POST /api/recepcion/pdf almacena el original en el bucket privado y encola la extracción/OCR. El límite es 20 MiB, 80 páginas y dos cargas simultáneas por proceso de API (429 con Retry-After cuando está ocupado). El OCR y el análisis se ejecutan en el worker.

GET /api/recepcion/catalogos devuelve empresas y analistas activos; exige recepcion.gestionar. POST /api/recepcion/expedientes recibe documento_id, procedimiento (CPI/UFI/RP), fecha_ingreso y asignado_a. Exige también asignacion.gestionar, PDF procesado si corresponde, fecha entre la del documento y hoy y analista activo. Devuelve 201 con tramite_id y version. Crea el expediente, incorpora el documento y conserva recepción, asignación y procedencia en una operación. Un documento también puede incorporarse a un expediente abierto existente, con su versión vigente y la misma EPS. Esa ruta devuelve 204 sin JSON.

El analista accede al expediente después de la asignación activa. Un listado vacío puede indicar ausencia de asignaciones y no justifica ampliar el ámbito de ese perfil.

## Alertas de calidad

GET /api/alertas añade reporte_faltante, avance_inconsistente, dato_duplicado, saldo_inconsistente y deposito_insuficiente. Son observaciones pendientes de verificación, con regla y referencias fuente; no determinan incumplimientos legales ni cambian el expediente automáticamente. Se restringen a las EPS de los expedientes visibles para la persona.

La ausencia de reportes se compara con el último trimestre disponible en los datos autorizados, excluyendo proyectos concluidos/cancelados. No se presupone un reporte futuro vencido. Los duplicados incluyen la cuarentena del importador. El saldo compara inicial + depósito + intereses − uso ejecutado − uso excepcional contra saldo final (tolerancia S/ 0,01; valores nulos no se convierten a cero). Los depósitos se agrupan por EPS/fondo, indicando número de registros inferiores al programado y número inferior al 50 %, con las últimas cinco referencias.

## Disponibilidad del agente

El chat documental mantiene los controles de ámbito y citas. Su generación y corrección tienen un presupuesto total de 35 segundos. Si el modelo falla o produce una respuesta no verificable, se pueden devolver extractos autorizados con una advertencia visible y modelo nulo; no se cachean ni se guardan como propuesta automática generada. Sin extractos disponibles se mantiene la respuesta de indisponibilidad o falta de fuentes. Los logs del proveedor incluyen códigos HTTP/tipos de error, sin claves ni contenido documental.

El panel de cartera consulta los endpoints de expedientes/alertas para preguntas de vencimientos o calidad; identifica que es una consulta de datos, sin análisis generado. Para preguntas documentales se abre el expediente.
