-- Ejecutar con administración de la base destino antes del backend de integración D3.
-- La verificación agrega una actuación de auditoría y enlaza el documento oficial
-- a la presentación informada. El rol técnico no modifica otros campos del historial.
BEGIN;
GRANT UPDATE (verificada,documento_id) ON actuacion TO yakukhipu_final_api;
COMMIT;
