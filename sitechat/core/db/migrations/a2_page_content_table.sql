CREATE TABLE IF NOT EXISTS page_chunks (
    id INTEGER PRIMARY KEY,
    page_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    UNIQUE(page_id, chunk_index),
    FOREIGN KEY(page_id) REFERENCES pages(id) ON DELETE CASCADE
);
