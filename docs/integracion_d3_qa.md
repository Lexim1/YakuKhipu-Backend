# Integración D3 en QA

El portal y la API comparten origen, PostgreSQL conserva los permisos y Keycloak el inicio OIDC. El worker existente mantiene PDF/OCR y OmniRoute. La integración no necesita un sexto servicio Railway.

## Orden del pase

1. Revisar los PR `feature/integracion-d3-qa → qa` de ambos repositorios. No es necesario pasar primero el frontend a master. El QA antiguo del backend está detrás de master: esta rama incorpora el master vigente para conservar OIDC, recepción, seguridad y worker ya integrados.
2. Restaurar el dump final en una **base QA distinta**. Si se usó `pg_restore --no-privileges`, restaurar los privilegios del rol técnico que figuran al final del SQL base.
3. Con administración de esa base, ejecutar `sql/migraciones/20261126_verificacion_respuesta.sql`. Solo concede UPDATE de `verificada` y `documento_id` en actuaciones, sin modificación general del historial. La verificación registra además su actuación de auditoría.
4. Generar, revisar y aplicar el lote D3 al destino explícito. Cargar los PDF en el bucket privado de ese entorno.
5. Usar un LOGIN que herede `yakukhipu_final_api` en `DATABASE_URL`, sin administración ni DDL. Configurar las identidades OIDC y asignaciones reales de QA.
6. Construir el portal con el commit del frontend fijado en `FRONTEND_COMMIT`. Validar QA antes del pase aprobado a master y producción. La validación local de esta entrega no despliega ni modifica Railway.

## Importación

Desde la raíz del backend, con `requirements.txt` instalado:

```powershell
python -m scripts.importar_d3 `
  --datasets 'D:\sunass\yakukhipu\mvp\D3_gestion_financiera\datos_sprint' `
  --actualizacion 'D:\sunass\yakukhipu\mvp\D3_gestion_financiera\datos_sprint\datos_para_demostracion\d3_actualizacion_al_2026-11-20' `
  --casos 'D:\sunass\yakukhipu\Casos reales' `
  --salida 'sql\local\d3-qa'
```

Por defecto genera SQL, manifiesto y copias documentales locales; no conecta a la BD ni a IA. `--casos` es opcional: admite los ZIP originales o las tres carpetas extraídas ya indexadas en el dump. Conserva sus estados y visibilidad; solo enlaza un original cuyo SHA-256 coincida con el registrado.

Configurar fuera de Git `D3_DATABASE_URL` con el destino verificado y repetir con `--aplicar`. Para el bucket, configurar las mismas variables `PDF_*` del portal y añadir `--subir-pdf`. El importador comprueba/sube hasta cuatro PDF simultáneamente y reutiliza objetos dirigidos por contenido. No crea trabajos de inferencia.

Sin bucket, `DOCUMENTOS_DIR` apunta a `<salida>\documentos`. Con bucket, los documentos usan `bucket:fuentes/d3/<sha256>.pdf` y no dependen de rutas de la PC en Railway. El bucket permanece privado: los PDF salen por los endpoints autorizados.

Se reemplaza por las claves indicadas en las instrucciones del sprint: expediente, expediente+hito, proyecto+trimestre, EPS+mes+fondo y actuación. Se conservan versiones revisadas, asignaciones, publicaciones y visibilidad. Los duplicados del mismo archivo se ponen en cuarentena.

Lote validado al 20 de noviembre de 2026: 501 procedimientos fuente, 1 874 hitos, 1 114 programas, 5 310 ejecuciones válidas de 5 334 filas, 3 303 fondos, 1 876 actuaciones y 1 805 entradas DS11. Hay 24 incidencias de calidad del lote de ejecución. Los 15 PDF ficticios contienen 130 documentos identificables: se separan y se comprueba el expediente de cada uno. Las demás entradas son índices, sin PDF entregado; no se descarga `sia.example`. Los 31 originales reales permanecen privados, dando 161 PDF fuente disponibles en total.

## Contratos y límites

- `/api/finanzas/resumen` y `/api/finanzas/eps/{id}` filtran las EPS del ámbito autorizado. El acumulado usa el último reporte por proyecto, sin sumar nuevamente cada trimestre. La ausencia de un dato permanece nula y la cobertura se muestra explícitamente. Los trimestres con distinta cobertura no producen un crecimiento porcentual comparable.
- Las duraciones entre hitos son días calendario observados, no plazos legales. Las reglas y calendarios requieren validación por su responsable.
- `/api/seguimiento/actuaciones`, `/encargos` y `/configuracion` consultan registros y permisos efectivos. No generan encargos ni vencimientos ficticios para completar pantallas. La configuración es de consulta.
- La EPS puede informar `referencia_presentada` antes de incorporar el PDF. El aviso queda sin verificar; SUNASS necesita un documento del mismo expediente y fecha acreditada para verificarlo. El campo anterior `documento` sigue admitiendo únicamente un ID visible para la EPS.
- La publicación usa `PUT /api/tramites/{id}/publicacion`, versión vigente y selección expresa de documentos. La ficha ciudadana solo expone la proyección aprobada y esas fuentes. No completa cifras públicas con datos institucionales internos.
- El lector documental permite texto por página y PDF autorizado. Cada lectura vuelve a comprobar permisos en el servidor.

## Pruebas sin inferencia

Mantener `LLM_ENABLED=false` y la clave vacía en el portal y worker QA. La suite usa modelos simulados y bloquea sockets externos. `VERIFY_DATABASE_URL` debe ser una copia PostgreSQL local: las escrituras de integración usan rollback. No ejecutar los tests contra producción.

```powershell
python -m pytest tests -ra
```

El frontend incluye contratos simulados y Playwright con Keycloak local real. El navegador cubre digital/OCR, derivación, actuación, presentación EPS, verificación con evidencia, publicación, fuentes, vistas operativas y CSV a 320 px. Bloquea destinos externos y chat, no guarda trazas ni contraseñas y solo admite hosts locales.

La inferencia real queda fuera de esta validación por la instrucción de no consumir OpenRouter. Los datos ficticios siguen identificados; los originales reales requieren revisión antes de publicarlos.
