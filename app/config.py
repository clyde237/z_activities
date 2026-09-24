import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "development-only-key")
    DATABASE_PATH = os.getenv(
        "DATABASE_PATH",
        str(Path("instance") / "app.sqlite3"),
    )
    # Si absente, déduite de DATABASE_PATH (SQLite local). La renseigner
    # directement permet de basculer vers PostgreSQL sans toucher au code.
    SQLALCHEMY_DATABASE_URI = os.getenv("SQLALCHEMY_DATABASE_URI")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    TESTING = False
