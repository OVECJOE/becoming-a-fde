CREATE TABLE IF NOT EXISTS chats (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL UNIQUE,
    history TEXT,
    last_user_prompt TEXT NOT NULL,
    last_ai_response TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    chat_id INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'ai')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);


CREATE INDEX IF NOT EXISTS idx_chat_title_created_at ON chats(title, created_at);
CREATE INDEX IF NOT EXISTS idx_chat_created_at_updated_at ON chats(created_at, updated_at);
CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id, created_at);
