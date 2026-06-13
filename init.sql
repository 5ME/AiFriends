CREATE USER aifriends WITH PASSWORD 'aifriends001#';
CREATE DATABASE aifriends OWNER aifriends;
GRANT ALL PRIVILEGES ON DATABASE aifriends TO aifriends;
-- 补充 schema 权限，避免建表失败
\c aifriends
GRANT ALL ON SCHEMA public TO aifriends;
CREATE EXTENSION IF NOT EXISTS vector;
