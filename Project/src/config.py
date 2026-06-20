from pathlib import Path
import os

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
IMAGING_EVENTS_DIR = DATA_DIR / "imaging_events"
RECALLS_FILE = DATA_DIR / "recalls" / "all_recalls.json"
REPORTS_DIR = PROJECT_ROOT / "outputs" / "reports"
RUNTIME_DIR = PROJECT_ROOT / "outputs" / "runtime"
LOGS_DIR = PROJECT_ROOT / "logs"
SQLITE_DB_PATH = RUNTIME_DIR / "signal_intelligence.db"
CHROMA_DIR = RUNTIME_DIR / "chroma"
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))

# Fixed starter scope requested by the team.
PRODUCT_CODES = ("LNH", "JAK", "LLZ")

DEFAULT_MAX_EVENTS_PER_CODE = 300
DEFAULT_COMPLAINT_BATCH = 12
DEFAULT_RANDOM_SEED = 42
