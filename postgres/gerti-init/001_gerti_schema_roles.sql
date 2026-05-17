-- ─────────────────────────────────────────────────────────────────────
--  PROD: introduz o schema `gerti` + roles + RLS no cluster Postgres VIVO
--  do Znuny (Spec #0: um cluster, dois schemas — `public`/Znuny + `gerti`).
--
--  Executado pelo serviço one-shot `gerti-db-init` (profile `gerti`) via
--  psql como o superusuário do cluster. NÃO é wired no
--  docker-entrypoint-initdb.d do serviço `postgres` (que só roda no 1º
--  init do cluster) — é um job dedicado, idempotente, gated por profile.
--
--  GARANTIAS (zero-tolerância, ver risk register do plano de deploy):
--   • Zero DROP. Zero escrita em objetos `public`/`znuny` do Znuny.
--   • Só CREATE ... IF NOT EXISTS / GRANT / ALTER ROLE / ALTER DEFAULT
--     PRIVILEGES — tudo idempotente, seguro p/ re-execução no cluster
--     com dados Znuny vivos.
--   • Senhas via variáveis psql (:sidecar_pw / :admin_pw já vêm com aspas
--     do compose) — nenhuma senha hardcoded em prod. ALTER ROLE PASSWORD
--     reaplica segredo rotacionado.
--
--  Byte-equivalente em GRANTS ao dev/test
--  (infra/compose/postgres/init/001_schemas_and_roles.sql) — zero drift.
-- ─────────────────────────────────────────────────────────────────────

\set ON_ERROR_STOP on

-- Schemas ------------------------------------------------------------
-- `znuny` fica vazio em prod (Znuny usa `public`); criado IF NOT EXISTS
-- para as futuras views read-only gerti→znuny (Spec #1E). Inócuo.
CREATE SCHEMA IF NOT EXISTS znuny;
CREATE SCHEMA IF NOT EXISTS gerti;

-- Extensões ---------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "btree_gin";

-- Roles NOLOGIN (sem senha) -----------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gerti_app') THEN
    CREATE ROLE gerti_app NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gerti_admin') THEN
    CREATE ROLE gerti_admin NOLOGIN BYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'znuny_owner') THEN
    CREATE ROLE znuny_owner NOLOGIN;
  END IF;
END $$;

-- Permissions -------------------------------------------------------
GRANT USAGE ON SCHEMA znuny TO gerti_app;
GRANT USAGE, CREATE ON SCHEMA gerti TO gerti_app, gerti_admin;
GRANT USAGE, CREATE ON SCHEMA znuny TO znuny_owner;

-- gerti_app só LÊ znuny (regra de ouro do ADR-003 / Spec #0)
ALTER DEFAULT PRIVILEGES FOR ROLE znuny_owner IN SCHEMA znuny
  GRANT SELECT ON TABLES TO gerti_app;

-- Usuários aplicacionais LOGIN — senha parametrizada, idempotente.
-- psql NÃO interpola :var dentro de bloco dollar-quoted, então o
-- create/alter condicional é feito com \gset + \if (fora de DO $$).

-- gerti_sidecar (RLS-subject, IN ROLE gerti_app, SEM BYPASSRLS)
SELECT NOT EXISTS (
  SELECT 1 FROM pg_roles WHERE rolname = 'gerti_sidecar'
) AS create_sidecar \gset
\if :create_sidecar
  CREATE USER gerti_sidecar PASSWORD :sidecar_pw IN ROLE gerti_app;
\else
  ALTER ROLE gerti_sidecar PASSWORD :sidecar_pw;
\endif

-- gerti_admin_user (BYPASSRLS via gerti_admin, dono do DDL/Alembic)
SELECT NOT EXISTS (
  SELECT 1 FROM pg_roles WHERE rolname = 'gerti_admin_user'
) AS create_admin \gset
\if :create_admin
  CREATE USER gerti_admin_user PASSWORD :admin_pw IN ROLE gerti_admin;
\else
  ALTER ROLE gerti_admin_user PASSWORD :admin_pw;
\endif

-- znuny LOGIN: em prod já existe (é o superusuário POSTGRES_USER) →
-- skip. Em cluster sem ele (paridade dev), cria sem senha utilizável
-- (NOLOGIN-equivalente: sem PASSWORD). Membership p/ as futuras views.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'znuny') THEN
    CREATE ROLE znuny LOGIN IN ROLE znuny_owner;
  END IF;
END $$;

-- Memberships idempotentes (no-op se já membro) — garante a relação
-- independente do ramo create/alter acima (rotação de segredo).
GRANT gerti_app   TO gerti_sidecar;
GRANT gerti_admin TO gerti_admin_user;

-- CRÍTICO: BYPASSRLS é ATRIBUTO de role e **NÃO é herdado por
-- membership** no Postgres (só privilégios de tabela são). `gerti_admin`
-- ter BYPASSRLS + `gerti_admin_user IN ROLE gerti_admin` NÃO faz o
-- usuário LOGIN bypassar RLS. O onboarding/seed admin (criar
-- znuny_instance/tenant, escrever em tabelas FORCE RLS) exige o atributo
-- DIRETO no usuário que loga. Idempotente; só superusuário pode setar
-- (este job roda como o superusuário do cluster). gerti_sidecar
-- permanece RLS-subject (NUNCA BYPASSRLS).
ALTER ROLE gerti_admin_user BYPASSRLS;
ALTER ROLE gerti_sidecar NOBYPASSRLS;

-- B4: toda tabela/sequence que o Alembic criar (como gerti_admin_user)
-- no schema gerti é auto-concedida a gerti_app — belt-and-suspenders
-- com os GRANTs por-migration (B2). FOR ROLE deve casar exatamente com
-- o role criador; declarativo/idempotente. APÓS gerti_admin_user existir.
ALTER DEFAULT PRIVILEGES FOR ROLE gerti_admin_user IN SCHEMA gerti
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO gerti_app;
ALTER DEFAULT PRIVILEGES FOR ROLE gerti_admin_user IN SCHEMA gerti
  GRANT USAGE, SELECT ON SEQUENCES TO gerti_app;

-- Verificação visual ------------------------------------------------
SELECT
  rolname,
  rolcanlogin,
  rolbypassrls,
  array(
    SELECT b.rolname FROM pg_auth_members m
    JOIN pg_roles b ON b.oid = m.roleid
    WHERE m.member = r.oid
  ) AS member_of
FROM pg_roles r
WHERE rolname LIKE 'gerti_%' OR rolname IN ('znuny', 'znuny_owner')
ORDER BY rolname;

SELECT nspname AS schema_ok
FROM pg_namespace WHERE nspname IN ('gerti', 'znuny') ORDER BY nspname;
