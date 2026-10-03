CREATE TABLE IF NOT EXISTS pages (
    id INTEGER PRIMARY KEY,
    url TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'in_progress', 'crawled', 'failed')),
    parent_url TEXT,
    depth INTEGER NOT NULL,
    crawled_at TEXT,
    created_at TEXT,
    content_hash TEXT
);

CREATE INDEX IF NOT EXISTS idx_page_status ON pages(status);
