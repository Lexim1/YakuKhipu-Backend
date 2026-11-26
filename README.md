# Backend YakuKhipu

FastAPI, SQLAlchemy y PostgreSQL 15+. La aplicación solo ejecuta consultas y DML. El único SQL versionado es `sql/yakukhipu_final.sql`.

## Instalación

Crear un entorno Python e instalar `requirements.txt`. Copiar `.env.example` a `.env`, establecer una SECRET_KEY aleatoria de al menos 32 caracteres, DATABASE_URL a yakukhipu_final y DOCUMENTOS_DIR a la carpeta de ZIP. COOKIE_SECURE=true en HTTPS; false solo en desarrollo HTTP.

Con psql, conectado inicialmente a postgres y fuera de una transacción:

```powershell
psql -U postgres -d postgres -v ON_ERROR_STOP=1 -f sql/yakukhipu_final.sql
```

Es una instalación NUEVA. El archivo crea yakukhipu_final y cambia la conexión con comandos de psql. No ejecutarlo completo en Query Tool de pgAdmin. No sobrescribe ni migra una BD existente y no debe repetirse sobre una BD ya instalada.

El SQL crea yakukhipu_final_api como rol técnico NOLOGIN. Crear una cuenta LOGIN propia, concederle ese rol y usarla en DATABASE_URL. Administrar usuarios/importaciones con otra cuenta; la aplicación no tiene DDL ni permisos de administrar cuentas.

Provisionar cuentas reales, sin cuentas de demo:

```powershell
python -m scripts.usuario_sql_final --id ID_REAL --nombre 'Nombre real' --rol analista_srt --oidc-issuer 'https://<keycloak>/realms/yakukhipu' --oidc-subject SUB_VERIFICADO
```

Roles: analista_srt, coordinacion_dre, jefatura_dre y eps. Solo EPS requiere --eps-id. Crea antes la cuenta individual en Keycloak y usa su `sub` verificado; el script no solicita contraseñas.

```powershell
python -m uvicorn app.main:app --reload
python -m pytest -ra
python -m scripts.exportar_openapi
```

## Organización

- app/auth: OIDC, sesiones persistentes y permisos.
- app/api: transporte HTTP y validación de entrada.
- app/modules: lógica por dominio (trámites, EPS, publicaciones, documentos, plazos y agente).
- app/repositories: filtros de acceso a expedientes/documentos.
- app/models y app/schemas: mapeos SQL y contratos HTTP.
- db: instrucciones de operación; sql: único entregable SQL.
- scripts: provisión, herramientas de fuentes, chat y exportación del contrato.
- tests/unit, tests/api y tests/integration: responsabilidades separadas.

## Seguridad y alcance

FastAPI inicia el acceso en Keycloak y vincula la identidad con un usuario del portal. La sesión usa una cookie HttpOnly firmada que identifica una sesión opaca persistida en seguridad.sesion. Logout revoca la sesión en la BD. La desactivación y el cambio de rol invalidan las sesiones. Los permisos se leen de seguridad.rol_permiso en cada petición. La API no ofrece ingreso con contraseña local.

La carga PDF crea una recepción y un trabajo persistente. El worker obtiene el original de un bucket privado, extrae el texto y aplica OCR en español cuando corresponde. Tras la incorporación autorizada, el agente usa los fragmentos por página. Consulta [el despliegue Railway](infra/railway/README.md).

La incorporación encola un análisis automático en `propuesta_agente`. El worker lo ejecuta cuando `LLM_ENABLED=true`, guarda la propuesta con sus citas y la expone solo a SUNASS en `GET /api/tramites/{id}/propuestas`. `POST /api/tramites/{id}/propuestas/{documento_id}/revision` requiere `evaluacion.validar` y un motivo para aceptar o rechazar. La revisión no modifica el estado del expediente.

Analista solo ve asignaciones activas; Coordinación y Jefatura ven la cartera CPI/UFI/RP. EPS solo ve su empresa. Publicaciones y documentos ciudadanos requieren habilitación expresa. Consultar trazabilidad no otorga permiso de modificarla. Los actos registrados con evidencia no equivalen a firmas o aprobaciones dentro del portal.

POST /api/tramites/{id}/asignaciones asigna o reasigna un analista activo; requiere asignacion.gestionar, versión vigente y motivo. La asignación previa se cierra y conserva.

## Fuentes y pruebas

scripts.generar_sql conserva las herramientas de lectura de datasets/casos. Sus salidas incrementales se generan en sql/local (ignorado por Git); no crean BD y no reemplazan automáticamente el SQL final. Revisar y conciliar cambios del dataset antes de actualizar una instalación existente. Los datos fuente simulados siguen identificados como tales; no hay semilla demo de ejecución.

Los tests unitarios y HTTP usan dobles y no prueban transacciones PostgreSQL. Para integración de solo lectura configurar VERIFY_DATABASE_URL y ejecutar tests/integration. Los PDF y ZIP no se versionan. El SQL final incluye texto fuente: revisar su contenido antes de redistribuirlo.
