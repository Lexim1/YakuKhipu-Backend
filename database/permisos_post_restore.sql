-- FUENTE: final/30_privilegios_postgres.sql
-- Rol técnico de ejecución; NO es un quinto perfil de personas del portal.
DO $$ BEGIN
 IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='yakukhipu_final_api') THEN
  CREATE ROLE yakukhipu_final_api NOLOGIN;
 END IF;
END $$;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA seguridad FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA seguridad FROM PUBLIC;
GRANT CONNECT ON DATABASE yakukhipu_final TO yakukhipu_final_api;
GRANT USAGE ON SCHEMA public,seguridad TO yakukhipu_final_api;
GRANT SELECT ON ALL TABLES IN SCHEMA public,seguridad TO yakukhipu_final_api;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA seguridad TO yakukhipu_final_api;
GRANT INSERT,UPDATE ON seguridad.sesion,seguridad.intento_acceso TO yakukhipu_final_api;
GRANT INSERT ON seguridad.evento_acceso TO yakukhipu_final_api;
GRANT INSERT,UPDATE,DELETE ON tramite,documento,fragmento,publicacion,documento_recibido,alerta,
 conversacion,mensaje,respuesta_cache,fuente,lote_importacion,registro_fuente,encargo
 TO yakukhipu_final_api;
GRANT INSERT ON actuacion,encargo_evento TO yakukhipu_final_api;
GRANT INSERT,UPDATE ON asignacion_tramite TO yakukhipu_final_api;
GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public,seguridad TO yakukhipu_final_api;
-- No concede DDL ni modificación de usuario, rol o rol_permiso; tampoco UPDATE/DELETE del historial.
-- Crear aparte una cuenta LOGIN con contraseña propia y concederle este rol.

GRANT SELECT ON seguridad.identidad_oidc TO yakukhipu_final_api;
GRANT SELECT,INSERT,DELETE ON seguridad.oidc_transaccion TO yakukhipu_final_api;
GRANT SELECT,INSERT,UPDATE ON procesamiento_pdf TO yakukhipu_final_api;
GRANT SELECT,INSERT,UPDATE ON propuesta_agente TO yakukhipu_final_api;
