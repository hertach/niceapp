# app/config.py
from pathlib import Path
from dotenv import load_dotenv
import os

# .env im Root laden (funktioniert unabhängig vom CWD)
load_dotenv(Path(__file__).parent.parent / '.env')

APP_TITLE       = os.getenv('APP_TITLE',  'NiceApp')
APP_LOGO        = os.getenv('APP_LOGO',   'app/static/icons/logo.png')
STORAGE_SECRET  = os.getenv('STORAGE_SECRET', 'fallback-secret-change-me')
DB_PATH         = os.getenv('DB_PATH',    'data/app.db')
PORT            = int(os.getenv('PORT',   '8080'))
RELOAD          = os.getenv('RELOAD', 'false').lower() == 'true'