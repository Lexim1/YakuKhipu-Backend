# Comprobación posterior a los PR aprobados — 26/11/2026

## Versiones y conexión

GitHub confirmó la fusión de frontend PR 32 (master 317af4b) y backend PR 13
(master 681fb43). Se actualizaron las dos ramas master locales con fast-forward,
sin cambios locales que proteger ni conflictos.

Portal y worker desplegaron el backend aprobado desde GitHub. La imagen obtiene
el frontend del commit 2d9f30f fijado en Dockerfile, incluido en el PR 32. El
JavaScript público /assets/index-BPnaOYRC.js responde 200 y contiene las rutas
/api/recepcion/catalogos y /api/recepcion/expedientes.

Ambos servicios usan postgres.railway.internal/yakukhipu_final. Keycloak usa
otro servidor: postgres-fcyt.railway.internal, base railway. No se publicó un
puerto de PostgreSQL ni se modificaron los datos fuente o el esquema.

## Corrección operativa aplicada

Aunque los PR estaban aprobados, portal y worker conservaban openrouter/free
y no tenían LLM_REASONING_EFFORT. Se configuraron en ambos servicios:

```text
LLM_MODEL=nvidia/nemotron-3.5-super-vl:free
LLM_REASONING_EFFORT=none
```

Se conservaron la clave existente, los permisos y los demás recursos. Los
despliegues resultantes terminaron en SUCCESS:

- Portal: de7f0246-0285-4699-8725-c0dd5253caad.
- Worker: 672fc03a-367a-4f74-b700-09a3cab8ad88.

El modelo pasó una llamada real de control con JSON válido. Esta llamada no
certifica una recomendación de negocio: el chat sigue exigiendo evidencia y
puede descartar una respuesta no verificable. No se fuerza none a otros modelos
que requieran razonamiento obligatorio.

## Pruebas realizadas

- Suite de código: 96 pruebas correctas con PostgreSQL local, incluidas seis
  integraciones. Las inserciones de esas pruebas se revirtieron.
- Navegador nuevo: página inicial, consulta ciudadana y redirección al formulario
  de Keycloak accesibles. La ciudadanía no necesita cuenta institucional.
- HTTP de nube: /, /sunass/expedientes, /eps/tramites y /ciudadania/decisiones
  devuelven HTML 200; /api/publico/decisiones y /api/publico/cifras devuelven
  JSON 200. /ready devuelve 200.
- /api/sesion, /api/tramites y /api/recepcion/catalogos anónimos devuelven 401.
  Una escritura con Origin ajeno devuelve 403.
- Inicio OIDC: cliente confidencial, Authorization Code, PKCE S256 y sin Direct
  Access Grants. El discovery, JWKS y autenticación del cliente pasaron. La
  redirección del portal crea una transacción persistente en la BD real.
- Bucket privado: escritura, lectura y eliminación del objeto sintético correctas.
- Muestra posterior al despliegue: cinco líneas del portal y dos del worker,
  sin trazas de error; consulta de HTTP 5xx de los últimos 20 minutos sin resultados.
  Esta muestra no representa una garantía de disponibilidad futura.
- Las comprobaciones de servicios externos se ejecutaron con la configuración
  real desde un contenedor local; la conexión privada SQL de producción se
  comprobó mediante sus rutas /ready, consulta pública e inicio OIDC. No se
  afirma haber ejecutado SSH ni una consulta SQL directa en el servidor.

## Cuentas y límites del resultado

Una consulta administrativa de solo lectura confirmó cuatro cuentas habilitadas
en Keycloak. Jefatura y Analista tienen el perfil completo y sin acciones
obligatorias pendientes. Coordinación y EPS conservan UPDATE_PASSWORD y campos
de perfil por completar. Deben establecer su contraseña personal y completar
esos datos en el primer ingreso; no se cambiaron sus contraseñas ni se eliminaron
esas acciones para omitir el paso. La sesión administrativa de auditoría se cerró.

No se ha certificado en esta comprobación el ingreso con las contraseñas personales
de los cuatro usuarios, el recorrido autenticado de navegador ni una nueva carga
operativa de PDF. Esas pruebas requieren una sesión de usuario y un documento
autorizado. Las pruebas automatizadas de roles no sustituyen ese recorrido.

Abrir dos conexiones de DataGrip no sincroniza bases y DataGrip no es necesario
para usar el portal. La nube sigue operativa con la PC de desarrollo apagada.
Un listado ciudadano vacío significa que todavía no hay decisiones publicadas;
un analista solo obtiene los expedientes que le han sido asignados. Ninguna de
esas situaciones autoriza publicar documentos internos o ampliar permisos.

El ajuste del validador y esta evidencia se entregan en una rama y PR nuevos;
no se escriben cambios directamente sobre master.
