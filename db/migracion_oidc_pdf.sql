\set ON_ERROR_STOP on
-- Ejecutar una sola vez en una instalación anterior, con la cuenta propietaria.
BEGIN;
ALTER TABLE usuario DROP CONSTRAINT usuario_activo_con_credencial;
CREATE TABLE seguridad.identidad_oidc (
 issuer text NOT NULL, subject text NOT NULL, usuario_id varchar(80) NOT NULL REFERENCES usuario(id),
 PRIMARY KEY(issuer, subject), CHECK(length(issuer)>0 AND length(subject)>0)
);
CREATE TABLE seguridad.oidc_transaccion (
 estado_hash varchar(64) PRIMARY KEY, navegador_hash varchar(64) NOT NULL,
 nonce text NOT NULL, verifier text NOT NULL, vence timestamptz NOT NULL DEFAULT now()+interval '10 minutes'
);
CREATE INDEX oidc_transaccion_vence ON seguridad.oidc_transaccion(vence);
CREATE TABLE procesamiento_pdf (
 recepcion_id text PRIMARY KEY REFERENCES documento_recibido(id), clave text NOT NULL UNIQUE,
 sha256 varchar(64) NOT NULL CHECK(sha256 ~ '^[0-9a-f]{64}$'), bytes integer NOT NULL CHECK(bytes BETWEEN 1 AND 20971520),
 estado text NOT NULL DEFAULT 'pendiente' CHECK(estado IN ('pendiente','procesando','listo','fallido')),
 intentos integer NOT NULL DEFAULT 0 CHECK(intentos >= 0), tomado timestamptz,
 creado timestamptz NOT NULL DEFAULT now(), paginas jsonb, error text,
 CHECK((estado='listo') = (paginas IS NOT NULL))
);
CREATE INDEX procesamiento_pdf_cola ON procesamiento_pdf(creado) WHERE estado IN ('pendiente','procesando');
CREATE TABLE propuesta_agente (
 documento_id varchar(120) PRIMARY KEY REFERENCES documento(id),
 tramite_id varchar(80) NOT NULL REFERENCES tramite(id),
 estado text NOT NULL DEFAULT 'pendiente' CHECK(estado IN ('pendiente','procesando','lista','sin_evidencia','fallida','aceptada','rechazada')),
 intentos integer NOT NULL DEFAULT 0 CHECK(intentos>=0),
 tomada timestamptz, creada timestamptz NOT NULL DEFAULT now(), actualizada timestamptz NOT NULL DEFAULT now(),
 propuesta text, fuentes jsonb NOT NULL DEFAULT '[]'::jsonb, advertencias jsonb NOT NULL DEFAULT '[]'::jsonb,
 modelo text, error text, revisada_por varchar(80) REFERENCES usuario(id), revision_motivo text, revisada_en timestamptz,
 CHECK ((estado IN ('lista','aceptada','rechazada')) = (propuesta IS NOT NULL)),
 CHECK ((revisada_en IS NOT NULL) = (estado IN ('aceptada','rechazada')))
);
CREATE INDEX propuesta_agente_cola ON propuesta_agente(creada) WHERE estado IN ('pendiente','procesando');
GRANT SELECT ON seguridad.identidad_oidc TO yakukhipu_final_api;
GRANT SELECT,INSERT,DELETE ON seguridad.oidc_transaccion TO yakukhipu_final_api;
GRANT SELECT,INSERT,UPDATE ON procesamiento_pdf TO yakukhipu_final_api;
GRANT SELECT,INSERT,UPDATE ON propuesta_agente TO yakukhipu_final_api;
COMMIT;
