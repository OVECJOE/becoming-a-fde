PRAGMA foreign_keys = OFF;

CREATE TABLE IF NOT EXISTS sites (
    id INTEGER PRIMARY KEY,
    domain TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE pages_new (
    id INTEGER PRIMARY KEY,
    site_id INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'in_progress', 'crawled', 'failed')),
    parent_url TEXT,
    depth INTEGER NOT NULL,
    crawled_at TEXT,
    created_at TEXT,
    content_hash TEXT,
    UNIQUE (site_id, url)
);

INSERT OR IGNORE INTO sites (domain, created_at)
SELECT DISTINCT
    lower(
        CASE
            WHEN instr(substr(url, instr(url, '//') + 2), '/') > 0 THEN substr(
                substr(url, instr(url, '//') + 2),
                1,
                instr(substr(url, instr(url, '//') + 2), '/') - 1
            )
            ELSE substr(url, instr(url, '//') + 2)
        END
    ),
    datetime('now')
FROM pages
WHERE instr(url, '//') > 0;

INSERT OR IGNORE INTO pages_new (
    id,
    site_id,
    url,
    status,
    parent_url,
    depth,
    crawled_at,
    created_at,
    content_hash
)
SELECT
    p.id,
    s.id,
    p.url,
    p.status,
    p.parent_url,
    p.depth,
    p.crawled_at,
    p.created_at,
    p.content_hash
FROM pages p
JOIN sites s
    ON s.domain = lower(
        CASE
            WHEN instr(substr(p.url, instr(p.url, '//') + 2), '/') > 0 THEN substr(
                substr(p.url, instr(p.url, '//') + 2),
                1,
                instr(substr(p.url, instr(p.url, '//') + 2), '/') - 1
            )
            ELSE substr(p.url, instr(p.url, '//') + 2)
        END
    );

DROP TABLE pages;
ALTER TABLE pages_new RENAME TO pages;

CREATE INDEX IF NOT EXISTS idx_pages_pending ON pages(site_id, status, id);
DROP INDEX IF EXISTS idx_page_status;

PRAGMA foreign_keys = ON;
