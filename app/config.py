import os
from datetime import timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB: str = os.getenv("MONGO_DB", "attendance_db")

# Timezone & Range limits
IST = timezone(timedelta(hours=5, minutes=30))
MAX_TREND_DAYS = 92
MIN_EPOCH_MS = 100_000_000_000         # 100 billion (rejects seconds)
MAX_EPOCH_MS = 4_102_444_800_000       # 2100-01-01T00:00:00Z
