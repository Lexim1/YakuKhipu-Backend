# Worker y OmniRoute en un servicio

Railway conserva cinco servicios: portal, worker, Keycloak, Postgres y KeycloakDB.
El worker usa `Dockerfile.worker` y `python -m app.worker_runtime`.
El supervisor inicia OmniRoute 3.8.54, configura proveedores y el combo `yakukhipu`
por su API de administración y después inicia `app.worker_pdf`, que también
procesa propuestas del agente. Si un proceso termina, el servicio falla para
que Railway lo reinicie. No requiere procesos en la computadora del desarrollador.

Se necesita un volumen montado en `/omniroute-data`. Allí se conservan SQLite,
las conexiones cifradas y `yakukhipu-inference-key.json` (modo 0600). Conservar
también `STORAGE_ENCRYPTION_KEY`, `API_KEY_SECRET` y `JWT_SECRET` entre despliegues.
La clave administrativa `OMNIROUTE_API_KEY` se mantiene exclusivamente en worker.
`YAKUKHIPU_OMNI_PROVIDERS` contiene la lista JSON de proveedores importados
(sourceId, provider, name, apiKey, providerSpecificData) y
`YAKUKHIPU_OMNI_COMBO` el combo JSON con sus modelos y connectionId de origen.
Estas variables son secretos de Railway; no se incluyen en Git.

OmniRoute escucha en el puerto privado 20128, con autenticación obligatoria y
modo headless; no se publica un dominio. Portal usa
`LLM_BASE_URL=http://worker.railway.internal:20128/v1`, `LLM_MODEL=yakukhipu`,
`LLM_ENABLED=true` y la clave de inferencia generada en el volumen. El worker
usa esa misma API por loopback. Las claves de Gemini/OpenRouter permanecen en
OmniRoute. Portal conserva Keycloak, base de datos y almacenamiento S3 existentes.

Railway comprueba `/health/ready` en `PORT=20127` (timeout de arranque 300 s).
La comprobación exige ambos procesos vivos y la API de OmniRoute disponible.
`OMNIROUTE_MEMORY_MB=320` limita el heap de Node; el consumo total incluye Python,
OCR y memoria nativa y debe observarse en Railway. Un volumen no añade servicios.
El servicio debe mantenerse activo (`sleepApplication=false`), con una réplica.

Portal conserva el `Dockerfile` habitual; únicamente worker usa `Dockerfile.worker`.
Ambos despliegan la rama `codex/worker-omniroute-cloud` mientras se revisa el PR.
No borrar esa rama antes de integrar el cambio y volver a enlazar los servicios a master.
`python -m app.validar_nube` admite HTTPS para proveedores externos y HTTP solamente
para `worker.railway.internal:20128` o `127.0.0.1:20128`, usados por OmniRoute.
