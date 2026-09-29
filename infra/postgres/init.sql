-- Papel da APLICAÇÃO: sem superuser, sem BYPASSRLS e não é dono das tabelas.
-- As tabelas são criadas pelo admin (migração do Store); o RLS vale para este papel.
CREATE ROLE edumetria_app LOGIN PASSWORD 'app_local_only' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
GRANT CONNECT ON DATABASE edumetria TO edumetria_app;
GRANT USAGE ON SCHEMA public TO edumetria_app;
ALTER DEFAULT PRIVILEGES FOR ROLE edumetria_admin IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO edumetria_app;
ALTER DEFAULT PRIVILEGES FOR ROLE edumetria_admin IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO edumetria_app;
