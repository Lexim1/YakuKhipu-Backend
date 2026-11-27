# Agente con fuentes y recomendación de carga

El conocimiento documental se mantiene en PostgreSQL y el bucket privado, no en los pesos del modelo. El agente ya usa recuperación de fuentes (RAG): autoriza el expediente, recupera pasajes, prepara el contexto, genera una respuesta y comprueba sus citas. Entrenar o cambiar de modelo no resuelve la falta de documentos, OCR, permisos o asignaciones.

## Funciones de esta rama

- `GET /api/agente/buscar?q=...&limite=5` localiza expedientes por referencia, EPS, título, etapa o analista autorizado, y documentos por título/número o contenido en español. Devuelve la ubicación en el portal, etapa, responsable y fuentes por página. No inventa una ubicación física de archivo. No llama a IA ni crea conversaciones.
- La búsqueda filtra primero el ámbito del usuario y la visibilidad de cada documento. El analista ve solo asignaciones activas; la EPS, sus expedientes y documentos para partes o públicos. La EPS no recibe nombres internos de analistas en los resultados. La búsqueda institucional exige sesión y `agente.consultar`; ciudadanía conserva la consulta del caso publicado.
- La recuperación de páginas usa búsqueda de texto de PostgreSQL. `sql/migraciones/20261127_busqueda_agente.sql` añade dos índices GIN opcionales para rendimiento. No requiere extensiones, embeddings pagados ni otro servicio Railway. [Documentación de PostgreSQL 18](https://www.postgresql.org/docs/18/textsearch-intro.html).
- Se limita el número de candidatos y resultados. Las coincidencias únicamente en el índice/número se distinguen de una página encontrada. Una página marcada para OCR no se usa como texto legible.
- `GET /api/asignaciones/carga`, los candidatos del expediente y el catálogo de recepción comparten el cálculo de carga. Cuentan expedientes distintos con asignación vigente, fuente presente, procedimiento CPI/UFI/RP y estado no concluido, autorizado ni no autorizado. Se excluyen cuentas inactivas y roles que no sean analistas SUNASS.
- Se ordena por carga ascendente; en empate, primero quien recibió su última asignación hace más tiempo, después nombre e ID. Todas las personas empatadas en la menor carga pueden aparecer recomendadas. La persona actualmente asignada no se recomienda para un cambio al mismo usuario. Si ya tiene la menor carga, se indica que puede conservarse.
- La recomendación es informativa: no asigna ni cambia responsabilidades automáticamente y no inventa una capacidad máxima. La carga puede cambiar entre la consulta y la confirmación; el formulario permite actualizarla. La confirmación conserva permiso, motivo, versión e historial.
- El agente responde las preguntas de carga consultando estos registros, sin modelo. La cabecera y el panel general comparten la búsqueda documental. Los enlaces permiten abrir el expediente y la fuente encontrada.

## Calidad de la respuesta

El control numérico ahora comprueba únicamente el extracto y encabezado enviados al modelo, no otra parte de la página que no recibió. Se invalida la versión anterior de la caché del agente. Para expedientes pequeños, el umbral BM25 se acota según el tamaño del corpus; una coincidencia pertinente de una sola página ya no se descarta solo por estar por debajo de 1.5.

Estos controles no prueban por sí solos la verdad de una interpretación. «La EPS solicitó 120 medidores» y «SUNASS autorizó 120 medidores» usan la misma cifra y pueden citar el mismo documento, pero no significan lo mismo. El prompt exige distinguir solicitado/autorizado/ejecutado; la respuesta se revisa con la página original. El agente no firma, decide ni avanza procedimientos.

Con `LLM_ENABLED=false`, la búsqueda y las recomendaciones funcionan igual. En una pregunta de expediente, si hay pasajes pertinentes, se pueden mostrar extractos de respaldo con sus fuentes y una advertencia de que no hubo análisis generado. No presentar esa prueba como una evaluación de la calidad del modelo real.

## Cómo incorporar conocimiento correctamente

1. Inventariar los originales que realmente existen; una entrada DS11 o una URL de ejemplo no equivalen a un PDF entregado.
2. Guardarlos en el bucket privado y vincularlos al expediente y EPS correctos. Las rutas de la PC no están disponibles dentro del contenedor Railway.
3. Extraer texto digital y procesar las páginas escaneadas con OCR. Revisar legibilidad, número de página y metadatos antes de considerar completos los documentos.
4. Conservar referencia, fecha, procedencia, versión y huella. La corrección de texto requiere invalidar su índice/caché; una versión nueva no convierte una fuente antigua en vigente.
5. Revisar visibilidad y asignaciones. Un analista sin fuentes en sus expedientes o una EPS sin documentos para partes no puede obtenerlas mediante un prompt.
6. Mantener un banco revisado por una persona con 30–50 preguntas: respuesta esperada, expediente, documento y página. Incluir paráfrasis, números de oficio, negaciones, solicitado/autorizado/ejecutado, documentos ausentes y accesos prohibidos.
7. Medir por separado: recuperación del documento/página entre los primeros resultados, exactitud de las citas, afirmaciones respaldadas, abstención cuando falta evidencia y cero acceso a casos ajenos. Evaluar la recuperación primero no consume inferencia; la evaluación de respuestas reales necesita un presupuesto explícito.

Durante una carga masiva, separar la extracción/OCR de las propuestas generadas. No habilitar trabajos masivos de IA para «entrenar» el conocimiento. La carga D3 del importador no crea propuestas ni publicaciones automáticas. El historial del chat tampoco constituye evidencia ni entrena el modelo.

## Validación y pase

La rama se prepara contra el master vigente para conservar sus flujos documentados. Integrar y revisar primero en QA. La imagen del portal debe fijar el commit del frontend de esta rama; el worker, portal, Keycloak y las dos bases existentes siguen siendo los cinco servicios Railway.

En una copia PostgreSQL local, `VERIFY_DATABASE_URL` habilita integración con rollback. Las pruebas verifican carga (abiertos frente a concluidos/históricos), empates, fuente/documento ausente, visibilidad, ámbito EPS/analista, búsqueda por página y por índice, permisos y el contexto efectivamente enviado al modelo. Los modelos de la suite son simulados y su red externa está bloqueada.

Las pruebas de navegador usan OIDC real local, datos ficticios explícitos y `LLM_ENABLED=false`. Cubren búsqueda, enlaces, citas, cambio de asignación con recálculo, respuesta extractiva y vista de 320 px. No despliegan ni cambian datos de Railway.
