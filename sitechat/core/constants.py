from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DB_MIGRATIONS_DIR = PROJECT_ROOT.joinpath("core/db/migrations")
NOISE_SELECTORS = ["script", "style", "nav", "footer", "header", "noscript", "svg"]
BLOCK_SELECTORS = "p, h1, h2, h3, h4, li"
RECOGNISED_SITEMAP_LOCATIONS = ["/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml", "/wp-sitemap.xml"]
