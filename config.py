import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(",")))
TIMEZONE = os.getenv("TIMEZONE", "Europe/Moscow")
BASE_DIR = Path(__file__).parent
DATABASE_URL = f"sqlite+aiosqlite:///{BASE_DIR}/database.db"