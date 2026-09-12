import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional


# Paths
def get_battery_home() -> Path:
    """Returns the base battery home directory."""
    return Path(os.environ.get("BATTERY_HOME", Path.home() / ".battery"))


def get_profiles_dir() -> Path:
    return get_battery_home() / "profiles"


def get_current_profile_file() -> Path:
    return get_battery_home() / "current_profile"


DEFAULT_HOME = get_battery_home()
PROFILES_DIR = get_profiles_dir()
CURRENT_PROFILE_FILE = get_current_profile_file()

DEFAULT_DB_PATH = Path(os.environ.get("BATTERY_DB_PATH", DEFAULT_HOME / "battery.db"))
DEFAULT_BATTERY_MD_PATH = Path(os.environ.get("BATTERY_MD_PATH", Path.cwd() / "BATTERY.md"))

# Embeddings & Retrieval constants
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

# RRF_K: Reciprocal Rank Fusion smoothing constant.
# Academic default is k=60 (tuned for TREC/MS-MARCO long-document retrieval).
# Empirically tuned on Battery's real-world corpus (92 engineering memories,
# 30 authentic dev queries) via grid sweep across k=[5,10,20,30,40,60] ×
# text_weight=[0.3–0.7]. Results (src/battery/evals/rrf_tuning_report.md):
#   k=5,  tw=0.5, vw=0.5 → MRR=0.8583, Hit@1=83.3%  ← OPTIMAL
#   k=10, tw=0.5, vw=0.5 → MRR=0.8567, Hit@1=83.3%
#   k=60, tw=0.5, vw=0.5 → MRR=0.8550, Hit@1=83.3%
# Lower k is better for short (1–3 sentence) factual assertions because rank
# positions carry more absolute signal vs. long document retrieval.
RRF_K = 5
DEFAULT_TEXT_WEIGHT = 0.5
DEFAULT_VEC_WEIGHT = 0.5

# Adaptive RRF: real-world corpus (≤92 items) peaks at tw=0.5; at 500+ memories BM25
# OR-matching injects noisy top ranks and tw=0.5 hybrid MRR regresses below vector-only.
# Grid sweep on stress-500 (2026-09-12): tw=0.1, vw=0.9 → MRR=0.8594 vs vector 0.8528.
LARGE_CORPUS_RRF_THRESHOLD = 200
LARGE_CORPUS_TEXT_WEIGHT = 0.1
LARGE_CORPUS_VEC_WEIGHT = 0.9

# Near-duplicate merge threshold (cosine similarity). See NEXT-2 in PRODUCT_ROADMAP.md.
NEAR_DUP_THRESHOLD = 0.88


def get_active_profile() -> str:
    """Returns the currently active context profile name."""
    env_profile = os.environ.get("BATTERY_PROFILE")
    if env_profile and env_profile.strip():
        return env_profile.strip()

    curr_file = get_current_profile_file()
    if curr_file.exists():
        try:
            profile = curr_file.read_text(encoding="utf-8").strip()
            if profile:
                return profile
        except Exception:
            pass

    return "default"


def set_active_profile(name: str) -> str:
    """Sets the active context profile."""
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Profile name cannot be empty.")
    if not re.match(r"^[a-zA-Z0-9_-]+$", clean_name):
        raise ValueError("Profile name must be alphanumeric with dashes or underscores only.")

    home_dir = get_battery_home()
    home_dir.mkdir(parents=True, exist_ok=True)
    get_current_profile_file().write_text(clean_name, encoding="utf-8")
    return clean_name


def get_profile_db_path(profile: Optional[str] = None) -> Path:
    """Resolves the SQLite database path for a given profile."""
    if os.environ.get("BATTERY_DB_PATH"):
        return Path(os.environ["BATTERY_DB_PATH"])

    prof = (profile or get_active_profile()).strip()
    if prof == "default":
        return get_battery_home() / "battery.db"
    return get_profiles_dir() / prof / "battery.db"


def get_profile_md_path(profile: Optional[str] = None) -> Path:
    """Resolves the BATTERY.md mirror path for a given profile."""
    if os.environ.get("BATTERY_MD_PATH"):
        return Path(os.environ["BATTERY_MD_PATH"])

    prof = (profile or get_active_profile()).strip()
    if prof == "default":
        return Path.cwd() / "BATTERY.md"
    return Path.cwd() / f"BATTERY_{prof.upper()}.md"


def list_profiles() -> List[Dict[str, Any]]:
    """Returns metadata for all available context profiles."""
    active_profile = get_active_profile()
    home_dir = get_battery_home()
    profiles_dir = get_profiles_dir()

    default_db = home_dir / "battery.db"
    profiles = {
        "default": {
            "name": "default",
            "is_active": active_profile == "default",
            "db_path": default_db,
            "exists": default_db.exists(),
        }
    }

    if profiles_dir.exists():
        for item in sorted(profiles_dir.iterdir()):
            if item.is_dir():
                prof_name = item.name
                db_file = item / "battery.db"
                profiles[prof_name] = {
                    "name": prof_name,
                    "is_active": active_profile == prof_name,
                    "db_path": db_file,
                    "exists": db_file.exists(),
                }

    if active_profile not in profiles:
        db_file = profiles_dir / active_profile / "battery.db"
        profiles[active_profile] = {
            "name": active_profile,
            "is_active": True,
            "db_path": db_file,
            "exists": db_file.exists(),
        }

    return list(profiles.values())


def delete_profile(name: str) -> bool:
    """Deletes an isolated profile. The default profile cannot be deleted."""
    clean_name = name.strip()
    if clean_name == "default":
        raise ValueError("The 'default' profile cannot be deleted.")

    prof_dir = get_profiles_dir() / clean_name
    deleted = False
    if prof_dir.exists():
        shutil.rmtree(prof_dir)
        deleted = True

    if get_active_profile() == clean_name:
        set_active_profile("default")
        deleted = True

    return deleted
