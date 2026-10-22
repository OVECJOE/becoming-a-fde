ALTER TABLE chats ADD COLUMN site_id INTEGER REFERENCES sites(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_chats_site_id ON chats(site_id);
