import os
from dotenv import load_dotenv

# Load env variables if running locally
load_dotenv()

# TELEGRAM
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", 0))

# SUPABASE
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

# GOOGLE SHEETS
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

# APP CONFIG
TIMEZONE = "Asia/Jakarta"
