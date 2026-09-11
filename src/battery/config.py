import os
from pathlib import Path

# Paths
DEFAULT_HOME = Path(os.environ.get("BATTERY_HOME", Path.home() / ".battery"))
DEFAULT_DB_PATH = Path(os.environ.get("BATTERY_DB_PATH", DEFAULT_HOME / "battery.db"))
DEFAULT_BATTERY_MD_PATH = Path(os.environ.get("BATTERY_MD_PATH", Path.cwd() / "BATTERY.md"))

# Embeddings & Retrieval constants
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384
RRF_K = 60
DEFAULT_TEXT_WEIGHT = 0.5
DEFAULT_VEC_WEIGHT = 0.5
