from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DATABASE_URL = PROJECT_ROOT.joinpath("sitechat.db")
DB_MIGRATIONS_DIR = PROJECT_ROOT.joinpath("core/db/migrations")
