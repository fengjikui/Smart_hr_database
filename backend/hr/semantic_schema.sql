-- V1 语义发布的可重建读模型：JSON 真源保存在 semantic/，这里不保存员工事实。
-- documents 存完整定义；search 只索引正向含义/别名，否定说明仍在定义正文中供模型理解。
CREATE TABLE IF NOT EXISTS semantic_documents (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, table_id TEXT,
 status TEXT NOT NULL, visibility TEXT NOT NULL, version TEXT NOT NULL,
 definition TEXT NOT NULL CHECK(json_valid(definition))
);
CREATE INDEX IF NOT EXISTS idx_semantic_kind_scope ON semantic_documents(kind,visibility,status);
-- trigram 是 SQLite 全文子串索引，不是向量召回或业务行权限过滤器。
CREATE VIRTUAL TABLE IF NOT EXISTS semantic_search USING fts5(id UNINDEXED,title,content,tokenize='trigram');
CREATE TABLE IF NOT EXISTS semantic_meta (key TEXT PRIMARY KEY,value TEXT NOT NULL);
