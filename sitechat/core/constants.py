from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DATABASE_URL = PROJECT_ROOT.joinpath("sitechat.db")
DB_MIGRATIONS_DIR = PROJECT_ROOT.joinpath("core/db/migrations")
NOISE_SELECTORS = ["script", "style", "nav", "footer", "header", "noscript", "svg"]
BLOCK_SELECTORS = "p, h1, h2, h3, h4, li"
