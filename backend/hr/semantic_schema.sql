CREATE TABLE IF NOT EXISTS semantic_documents (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, table_id TEXT,
 status TEXT NOT NULL, visibility TEXT NOT NULL, version TEXT NOT NULL,
 definition TEXT NOT NULL CHECK(json_valid(definition))
);
CREATE INDEX IF NOT EXISTS idx_semantic_kind_scope ON semantic_documents(kind,visibility,status);
CREATE VIRTUAL TABLE IF NOT EXISTS semantic_search USING fts5(id UNINDEXED,title,content,tokenize='trigram');
CREATE TABLE IF NOT EXISTS semantic_meta (key TEXT PRIMARY KEY,value TEXT NOT NULL);
