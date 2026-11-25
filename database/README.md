# Dump de instalación para DataGrip

`yakukhipu_final.dump` es un archivo binario comprimido creado con `pg_dump -Fc`
de PostgreSQL 17. Contiene tablas, constraints, índices, vistas, funciones,
perfiles/permisos y los datos de `sql/yakukhipu_final.sql` de la entrega BK-1.
No es un SQL para pegar en el editor ni un backup de la base activa de Railway.

No contiene cuentas reales, contraseñas, sesiones ni identidades OIDC de Railway.
La definición de las tablas de autenticación sí está incluida. Los roles globales
de PostgreSQL y sus contraseñas no forman parte de un dump de una base.
Los datos simulados proporcionados por los datasets conservan su procedencia.

## Restaurar en DataGrip

1. Conecta DataGrip al servidor PostgreSQL de destino usando host, puerto, usuario,
   contraseña y SSL indicados por su administrador. Comprueba la conexión.
2. Crea una base **nueva y vacía**, `yakukhipu_final`, con UTF8. Si ya existe,
   respáldala y pide una base nueva; esta guía no sobrescribe bases existentes.
3. Haz clic derecho sobre esa base en Database Explorer → **Import/Export →
   Restore with pg_restore**. Selecciona `yakukhipu_final.dump` como archivo.
4. En Path to executable elige `pg_restore.exe` de PostgreSQL 17 o superior.
   En este equipo está instalado en `C:\Program Files\PostgreSQL\18\bin\pg_restore.exe`.
5. Añade `--no-owner --no-privileges --exit-on-error`. No actives Clean/Drop ni
   Create database: el destino ya debe estar vacío y seleccionado. Ejecuta Restore.
6. Con el administrador de la BD, abre y ejecuta `permisos_post_restore.sql`
   **conectado a la base restaurada**. Si usaste otro nombre de base, cambia la
   línea `GRANT CONNECT ON DATABASE yakukhipu_final` para ese nombre.
7. Crea aparte un LOGIN de aplicación con contraseña privada, concédele
   `yakukhipu_final_api` y configura su URL en `DATABASE_URL`. No uses el dueño
   de la base como usuario de la API ni publiques su contraseña.
8. Provisiona las cuentas Keycloak y los vínculos `seguridad.identidad_oidc`
   para los usuarios reales. El dump de instalación no habilita cuentas de demo.

Ejemplo equivalente en PowerShell (solicita la contraseña; no la guarda):

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\pg_restore.exe' -h HOST -p PUERTO -U USUARIO -d yakukhipu_final --no-owner --no-privileges --exit-on-error .\database\yakukhipu_final.dump
& 'C:\Program Files\PostgreSQL\18\bin\psql.exe' -h HOST -p PUERTO -U USUARIO -d yakukhipu_final -v ON_ERROR_STOP=1 -f .\database\permisos_post_restore.sql
```

No ejecutes además el SQL instalador completo sobre la base restaurada: ambos
son alternativas para instalar la misma estructura y datos.

## Verificación

Tras restaurar se esperan 484 trámites, 31 documentos y 729 fragmentos. El portal
filtra CPI, UFI y RP; los otros procedimientos del dataset permanecen en la BD.
`usuario` y `seguridad.sesion` deben tener cero filas en esta entrega.
Verifica el SHA256 del archivo con `Get-FileHash -Algorithm SHA256` y compáralo
con `manifest.json`.

Referencias: [importación en DataGrip](https://www.jetbrains.com/help/datagrip/import-data.html)
y [pg_restore de PostgreSQL](https://www.postgresql.org/docs/17/app-pgrestore.html).
