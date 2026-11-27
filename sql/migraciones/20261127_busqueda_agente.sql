-- Índices opcionales para la búsqueda. Ejecutar con administración de la BD
-- destino; el proceso de la aplicación nunca crea índices ni extensiones.
BEGIN;
CREATE INDEX IF NOT EXISTS fragmento_busqueda_es ON fragmento
  USING gin (to_tsvector('spanish',coalesce(texto,''))) WHERE NOT requiere_ocr;
CREATE INDEX IF NOT EXISTS documento_busqueda_es ON documento
  USING gin (to_tsvector('spanish',coalesce(titulo,'')||' '||coalesce(referencia,'')));
COMMIT;
