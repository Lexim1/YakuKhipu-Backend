# Despliegue real de YakuKhipu en Railway

Son seis recursos: PostgreSQL de YakuKhipu, PostgreSQL exclusivo de Keycloak,
Keycloak, un bucket privado y dos servicios del repositorio (portal y worker).
Este repositorio construye FastAPI y el worker. El frontend se publica aparte
y debe enviar `/api` mediante un proxy del mismo origen para conservar el BFF.
El worker no tiene dominio público. No se guardan credenciales en Git.

## 1. PostgreSQL

Crea `YakuKhipuDB` y `KeycloakDB` como servicios PostgreSQL separados.
Ejecuta `sql/yakukhipu_final.sql` con **psql**, conectado inicialmente
a la base de mantenimiento. Contiene `CREATE DATABASE` y `\connect`; el
editor SQL de DataGrip no interpreta este último comando. En una instalación
existente, respalda primero y aplica una vez `db/migracion_oidc_pdf.sql`
conectado a `yakukhipu_final`. No uses el instalador completo como migración.

El SQL crea el rol `yakukhipu_final_api` sin LOGIN. Crea una cuenta LOGIN
separada, miembro de ese rol, para portal y worker. Guarda su contraseña en
Railway. `DATABASE_URL` debe apuntar por red privada a `yakukhipu_final` y
usar `postgresql+psycopg://`.

## 2. Keycloak

Crea un servicio desde la imagen oficial `quay.io/keycloak/keycloak` con
comando `start` y dominio HTTPS. No uses `start-dev`. Variables:

| Variable | Valor |
| --- | --- |
| `KC_DB` | `postgres` |
| `KC_DB_URL` | `jdbc:postgresql://${{KeycloakDB.PGHOST}}:${{KeycloakDB.PGPORT}}/${{KeycloakDB.PGDATABASE}}` |
| `KC_DB_USERNAME` | `${{KeycloakDB.PGUSER}}` |
| `KC_DB_PASSWORD` | `${{KeycloakDB.PGPASSWORD}}` |
| `KC_HOSTNAME` | `https://<dominio-real-de-keycloak>` |
| `KC_HTTP_ENABLED` | `true` |
| `KC_PROXY_HEADERS` | `xforwarded` |
| `KC_BOOTSTRAP_ADMIN_USERNAME` | administrador inicial |
| `KC_BOOTSTRAP_ADMIN_PASSWORD` | contraseña inicial, secreto |

Keycloak escucha HTTP 8080 detrás del proxy TLS de Railway. En su consola crea
el realm `yakukhipu`, sin autorregistro, y un cliente OIDC confidencial
`yakukhipu-portal`: Standard Flow y Client Authentication activos, Direct
Access Grants desactivado, PKCE S256 y firma RS256. Registra exactamente:

- Redirect URI: `https://<portal>/api/auth/callback`
- Post logout redirect URI: `https://<portal>/`
- Web origin: `https://<portal>`

`OIDC_ISSUER` debe coincidir exactamente con el `issuer` de
`https://<keycloak>/realms/yakukhipu/.well-known/openid-configuration`.
Crea cuentas reales en Keycloak y vincula su `sub` verificado con la cuenta
local en `seguridad.identidad_oidc`. Desde la raíz genera el alta SQL:

```sh
python -m scripts.usuario_sql_final --id ID_REAL --nombre "Nombre" --rol analista_srt --oidc-issuer "https://<keycloak>/realms/yakukhipu" --oidc-subject "SUB_VERIFICADO"
```

Para `eps`, añade `--eps-id ID_EPS`. Aplica el SQL como propietario de la
base. Los cuatro roles son `analista_srt`, `coordinacion_dre`,
`jefatura_dre` y `eps`; los permisos se leen de PostgreSQL.

## 3. Bucket privado

Crea un Bucket de Railway. En portal y worker referencia sus credenciales;
cambia `PDFBucket` por el nombre real del recurso:

| Variable de YakuKhipu | Referencia Railway |
| --- | --- |
| `PDF_BUCKET` | `${{PDFBucket.BUCKET}}` |
| `PDF_ENDPOINT` | `${{PDFBucket.ENDPOINT}}` |
| `PDF_REGION` | `${{PDFBucket.REGION}}` |
| `PDF_ACCESS_KEY` | `${{PDFBucket.ACCESS_KEY_ID}}` |
| `PDF_SECRET_KEY` | `${{PDFBucket.SECRET_ACCESS_KEY}}` |
| `PDF_ADDRESSING_STYLE` | `virtual` o `path`, según Credentials |

Usa `BUCKET`, no `RAILWAY_BUCKET_NAME`. El PDF original permanece privado
y la API lo entrega solo con autorización. Railway Buckets no ofrece hoy
cifrado S3 del lado del servidor ni versionado; confirma que cumple la política
aplicable antes de cargar expedientes sensibles.

## 4. Portal, worker y agente real

Construye portal y worker desde la **raíz** con el `Dockerfile`. Portal:
comando por defecto, dominio HTTPS, healthcheck `/ready`. Worker:
`python -m app.worker_pdf`, sin dominio público y sin suspensión por
inactividad. GitHub solo despliega archivos publicados en la rama conectada;
los cambios locales sin commit requieren `railway up` desde el repositorio
después de enlazar cada servicio con el CLI.

Variables del portal:

| Variable | Valor |
| --- | --- |
| `DATABASE_URL` | URL privada de `yakukhipu_final`, esquema `postgresql+psycopg://` |
| `SECRET_KEY` | valor aleatorio único de 32 caracteres o más |
| `COOKIE_SECURE` | `true` |
| `PORTAL_ORIGIN`, `FRONTEND_ORIGIN` | mismo origen HTTPS del portal |
| `OIDC_ISSUER` | issuer exacto del realm |
| `OIDC_CLIENT_ID` | `yakukhipu-portal` |
| `OIDC_CLIENT_SECRET` | secreto de Keycloak |
| `LLM_ENABLED` | `true` tras configurar clave y modelo |
| `LLM_BASE_URL` | URL HTTPS compatible con `/chat/completions` |
| `LLM_API_KEY` | clave real del proveedor |
| `LLM_MODEL` | ID del modelo disponible |

El repositorio propone OpenRouter por defecto: `LLM_BASE_URL=https://openrouter.ai/api/v1`
y `LLM_MODEL=openrouter/free`. Es un proveedor real, pero necesita una clave de
tu cuenta de OpenRouter; `openrouter/free` selecciona modelos gratuitos de forma
variable y tiene límites de uso. Para una validación reproducible conviene fijar
un modelo concreto tras probarlo con la cuenta. Nunca pegues la clave en Git.

El worker requiere `DATABASE_URL`, las seis variables `PDF_*` y las cuatro
`LLM_*` (`LLM_ENABLED`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`).
Sin `LLM_ENABLED=true` en el worker, la propuesta automática queda pendiente.
El texto extraído de los PDF se envía al proveedor del modelo; usa documentos
de piloto autorizados y verifica sus reglas de tratamiento. Deja
`FECHA_DEMO` vacía.

## 5. Comprobación de servicios reales

Desde el contenedor del portal desplegado:

```sh
railway ssh --service portal -- python -m app.validar_nube
```

Comprueba esquema PostgreSQL, discovery/JWKS y cliente Keycloak,
escritura/lectura/borrado de un objeto sintético en el bucket y una llamada
real al modelo. Sale con código 1 ante fallos y no imprime secretos.

Después prueba en navegador login y logout, `GET /api/sesion`, accesos por
rol, subida de PDF autorizado, procesamiento `listo`, incorporación al
expediente, propuesta `lista` con citas y revisión por un rol con
`evaluacion.validar`. El script no reemplaza ese recorrido.

Referencias: [Railway Buckets](https://docs.railway.com/storage-buckets),
[variables](https://docs.railway.com/variables),
[SSH](https://docs.railway.com/cli/ssh) y
[Keycloak en producción](https://www.keycloak.org/server/configuration-production).
