# Contrato HTTP vigente

La fuente exacta de rutas, entradas y salidas es [openapi.json](openapi.json), generado con python -m scripts.exportar_openapi desde backend.

## Sesión

POST /api/sesion recibe usuario_id y password. GET /api/sesion devuelve usuario_id, nombre, perfil (sunass/eps), rol_id, permisos, eps_id y eps. DELETE /api/sesion revoca la sesión persistente y devuelve 204. Usar credentials: include en el navegador. La cookie HttpOnly firmada vence en ocho horas; no hay token JWT ni login demo.

GET /health incluye `ingreso` y `carga_pdf`. Con `ingreso: "oidc"` (OIDC_ISSUER o PORTAL_ORIGIN configurados) POST /api/sesion responde 401 y el portal debe enlazar a GET /api/auth/login; Keycloak vuelve a /api/auth/callback, que abre la sesión y redirige a /sunass/expedientes o /eps/tramites (o a /?acceso=fallido). DELETE /api/sesion puede devolver la cabecera X-Logout-URL para cerrar también la sesión en Keycloak. Con `ingreso: "clave"` se usa POST /api/sesion. `carga_pdf: "habilitada"` indica que hay bucket para POST /api/recepcion/pdf. En OIDC el portal y la API deben compartir origen (proxy de /api).

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

El frontend existente aún no implementa este flujo de sesión ni los tres menús SUNASS. Su integración está fuera de esta corrección.
