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


def _truthy(value: str | None) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


# --- LangSmith observability -------------------------------------------------
# Accept both the legacy LANGCHAIN_* names and the newer LANGSMITH_* aliases so
# either style in .env works. The key/endpoint stay in .env (never committed).
LANGSMITH_TRACING = _truthy(os.getenv("LANGCHAIN_TRACING_V2") or os.getenv("LANGSMITH_TRACING"))
LANGSMITH_API_KEY = os.getenv("LANGCHAIN_API_KEY") or os.getenv("LANGSMITH_API_KEY")
LANGSMITH_PROJECT = (
    os.getenv("LANGCHAIN_PROJECT")
    or os.getenv("LANGSMITH_PROJECT")
    or "regulatory-signal-intelligence"
)
LANGSMITH_ENDPOINT = (
    os.getenv("LANGCHAIN_ENDPOINT")
    or os.getenv("LANGSMITH_ENDPOINT")
    or "https://api.smith.langchain.com"
)

# Fixed starter scope requested by the team.
PRODUCT_CODES = ("LNH", "JAK", "LLZ")

DEFAULT_MAX_EVENTS_PER_CODE = 300
DEFAULT_COMPLAINT_BATCH = 12
DEFAULT_RANDOM_SEED = 42
