# Flujo de cambios

Cada cambio funcional se desarrolla en una rama nueva desde `master`, con nombre
`feature/BK-N`, y se entrega mediante un PR hacia `qa`. Después de validar en QA,
la administradora integra a `master`. No publicar cambios funcionales directamente
en las ramas base.

Este repositorio contiene solo backend. La API y el worker se construyen desde
el Dockerfile de la raíz. Para el worker usar `python -m app.worker_pdf`.

En el despliegue BFF, el frontend debe publicar `/api` bajo el mismo origen del
portal mediante su proxy. Configurar los callback OIDC y los orígenes con ese
dominio. Separar repositorios no cambia automáticamente la infraestructura de
Railway que ya fue validada.

No versionar `.env`, contraseñas, claves, sesiones ni exportaciones de la base
operativa. El dump de instalación se entrega en un PR independiente y se genera
exclusivamente desde `sql/yakukhipu_final.sql`.
