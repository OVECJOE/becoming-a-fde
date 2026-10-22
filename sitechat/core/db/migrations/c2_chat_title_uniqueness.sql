PRAGMA foreign_keys = OFF;

CREATE TABLE chats_new (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    site_id INTEGER REFERENCES sites(id) ON DELETE SET NULL,
    history TEXT,
    last_user_prompt TEXT NOT NULL,
    last_ai_response TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

INSERT INTO chats_new (
    id,
    title,
    site_id,
    history,
    last_user_prompt,
    last_ai_response,
    created_at,
    updated_at
)
SELECT id, title, site_id, history, last_user_prompt, last_ai_response, created_at, updated_at
FROM chats;

DROP TABLE chats;
ALTER TABLE chats_new RENAME TO chats;

CREATE INDEX IF NOT EXISTS idx_chat_title_created_at ON chats(title, created_at);
CREATE INDEX IF NOT EXISTS idx_chat_created_at_updated_at ON chats(created_at, updated_at);
CREATE INDEX IF NOT EXISTS idx_chats_site_id ON chats(site_id);

PRAGMA foreign_keys = ON;
