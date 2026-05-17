-- Executado pelo entrypoint oficial da imagem postgres:16 quando o cluster
-- é inicializado pela primeira vez. Idempotente para permitir re-execução
-- manual em ambiente dev.

-- Schemas ------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS znuny;
CREATE SCHEMA IF NOT EXISTS gerti;

-- Extensões ---------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "pgcrypto";  -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "btree_gin";

-- Roles -------------------------------------------------------------
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

-- gerti_app só lê znuny (regra de ouro do ADR-003)
ALTER DEFAULT PRIVILEGES FOR ROLE znuny_owner IN SCHEMA znuny
  GRANT SELECT ON TABLES TO gerti_app;

-- Usuários aplicacionais --------------------------------------------
-- senhas via variável passada no docker-compose; aqui só placeholders
-- (re-executar via SQL em prod com senhas reais do Vault)
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gerti_sidecar') THEN
    CREATE USER gerti_sidecar PASSWORD 'dev_change_me' IN ROLE gerti_app;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gerti_admin_user') THEN
    CREATE USER gerti_admin_user PASSWORD 'dev_change_me' IN ROLE gerti_admin;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'znuny') THEN
    CREATE USER znuny PASSWORD 'dev_change_me' IN ROLE znuny_owner;
  END IF;
END $$;

-- Verificação visual ------------------------------------------------
SELECT
  rolname,
  rolbypassrls,
  array(SELECT b.rolname FROM pg_auth_members m JOIN pg_roles b ON b.oid = m.roleid WHERE m.member = r.oid) AS roles
FROM pg_roles r
WHERE rolname LIKE 'gerti_%' OR rolname IN ('znuny', 'znuny_owner');
