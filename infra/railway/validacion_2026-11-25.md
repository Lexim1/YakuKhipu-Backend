# Validación real de Railway — 25 de noviembre de 2026

Evidencia del despliegue original desde el monorepositorio YakuKhipu, anterior
a su separación. No certifica un nuevo despliegue desde este repositorio.

Proyecto privado: `116b380d-82c3-404d-88b1-045fbe74a526`.

- Portal: https://portal-production-755de7de.up.railway.app
- Keycloak: https://keycloak-production-e95e3b8d.up.railway.app
- Issuer: https://keycloak-production-e95e3b8d.up.railway.app/realms/yakukhipu
- Servicios: portal, worker, Keycloak, Postgres, KeycloakDB y PDFBucket.

Se importó `sql/yakukhipu_final.sql` en `yakukhipu_final` mediante un
túnel SSH local; no se habilitó un proxy TCP público de PostgreSQL. El portal y
worker usan el LOGIN limitado `yakukhipu_app`, miembro de
`yakukhipu_final_api`, y la URL privada de Railway. Conteos al terminar la
importación: 484 trámites, 31 documentos y 729 fragmentos. Estos conteos incluyen
lo que conserva el SQL fuente; el portal filtra CPI, UFI y RP.

Se configuró el puerto 8000 del portal para coincidir con su dominio público.
React y FastAPI se sirven bajo el mismo origen HTTPS. El worker usa
`python -m app.worker_pdf`, sin dominio público. Los cambios se desplegaron
desde los archivos locales, sin publicar commits en GitHub.

## Pruebas reales: 75 de 75 correctas

Se ejecutaron solicitudes HTTP al portal desplegado, autenticación real en
Keycloak, consultas a PostgreSQL de Railway y procesamiento real en el worker.
No se sustituyeron el proveedor OIDC, el almacenamiento ni el modelo por mocks.
Las cuentas, expedientes y el PDF de prueba fueron fixtures temporales,
identificados como validación y retirados al terminar.

- `/live` y `/ready`: HTTP 200; sesión anónima y expedientes sin autenticar: 401.
- Escrituras sin Origin del portal: 403.
- Login Authorization Code + PKCE S256 y callback real para los cuatro roles.
- Código OIDC consumido: reutilización rechazada.
- Perfil y cookie Secure/HttpOnly verificados para cada rol.
- Lectura de ficha y trazabilidad de CPI, UFI y RP según asignación y alcance.
- Analista y EPS sin acceso a Recepción: 403; expediente de otra EPS: 404.
- Carga de archivo falso: 422.
- PDF temporal guardado en bucket y encolado: 202.
- Página digital extraída como `texto_pdf`; página escaneada procesada como `ocr`.
- Incorporación del documento a un expediente CPI: 204.
- Analista asignado consulta la página OCR; EPS no accede al PDF interno.
- Propuesta automática guardada en estado `lista`, con citas al documento,
  usando OpenRouter real desde el worker.
- Coordinación no puede validar evaluación: 403; analista autorizado: 200.
- Logout y posterior 401 comprobados para los cuatro perfiles.

Además se verificó escritura/lectura de un objeto real del bucket y rechazo del
acceso anónimo. El objeto fue eliminado después de la prueba.

## Alcance y pendientes de operación

Estas pruebas validan el despliegue y el recorrido descrito; no equivalen a
probar cada transición de negocio de los tres procedimientos ni a una auditoría
de seguridad completa. El recorrido de carga, OCR y propuesta se probó en CPI;
las fichas y trazabilidad se probaron también en UFI y RP.

OpenRouter usa `openrouter/free`, con selección variable de modelos y límites
de cuota. Portal y worker tienen `LLM_ENABLED=true`. No hay secretos en este
documento. Una clave compartida por chat debe rotarse después de la validación.

Las cuentas reales deben crearse en Keycloak y vincularse en
`seguridad.identidad_oidc` con el rol y EPS correctos. No se dejan usuarios de
prueba como cuentas de operación. Se creó la cuenta inicial `valp092` con
perfil `jefatura_dre`, vinculada a OIDC, con contraseña temporal y cambio
obligatorio al primer ingreso. La credencial se guardó cifrada con DPAPI fuera
del repositorio. La clave SSH temporal fue retirada de Railway al terminar.
