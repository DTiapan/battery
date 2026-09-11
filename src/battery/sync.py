import re

try:
    import pysqlite3 as sqlite3
except ImportError:
    import sqlite3
from pathlib import Path
from typing import Dict, List

from battery.config import DEFAULT_BATTERY_MD_PATH
from battery.db import hash_content, insert_memory, list_memories
from battery.embeddings import embed_text

CATEGORY_TITLES = {
    "rule": "Active Rules & Constraints",
    "decision": "Architectural Decisions",
    "preference": "User Preferences & Habits",
    "general": "General Knowledge & Context",
    "episodic": "Session Checkpoints & Episodic Memory",
}


def export_battery_md(conn: sqlite3.Connection, md_path: Path = DEFAULT_BATTERY_MD_PATH) -> Path:
    """Exports all non-deleted memories to a formatted living Markdown file."""
    memories = list_memories(conn, include_deleted=False, limit=500)

    # Group by category
    grouped: Dict[str, List[dict]] = {cat: [] for cat in CATEGORY_TITLES}
    for m in memories:
        cat = m["category"].lower()
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append(m)

    lines = [
        "# Battery Context Engine — Living Memory Mirror",
        "",
        "> **Notice:** This file mirrors the active state of your local sovereign memory database (`battery.db`).",
        "> It is git-committable and human-editable. Edits and additions will synchronize back to the engine.",
        "",
    ]

    for cat_key, section_title in CATEGORY_TITLES.items():
        items = grouped.get(cat_key, [])
        if items:
            lines.append(f"## {section_title}")
            lines.append("")
            for item in items:
                lines.append(f"- **[ID:{item['id']}]** {item['content']}")
            lines.append("")

    # Include any custom categories
    for cat_key, items in grouped.items():
        if cat_key not in CATEGORY_TITLES and items:
            lines.append(f"## {cat_key.capitalize()}")
            lines.append("")
            for item in items:
                lines.append(f"- **[ID:{item['id']}]** {item['content']}")
            lines.append("")

    content = "\n".join(lines).strip() + "\n"

    # Write atomically using a temporary file
    temp_path = md_path.with_suffix(".tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(md_path)
    return md_path


def import_battery_md(conn: sqlite3.Connection, md_path: Path = DEFAULT_BATTERY_MD_PATH) -> int:
    """Parses a BATTERY.md file and synchronizes any new or modified memories."""
    if not md_path.exists():
        return 0

    text = md_path.read_text(encoding="utf-8")
    current_category = "general"
    inserted_count = 0

    category_reverse_map = {title.lower(): key for key, title in CATEGORY_TITLES.items()}

    for line in text.splitlines():
        line = line.strip()
        if line.startswith("## "):
            section = line[3:].strip().lower()
            current_category = category_reverse_map.get(section, section)
            continue

        if line.startswith("- "):
            item_text = line[2:].strip()
            # Strip optional [ID:xyz] prefix if present
            clean_content = re.sub(r"^\*\*\[ID:\d+\]\*\*\s*", "", item_text).strip()
            if clean_content:
                # Check if hash already exists
                c_hash = hash_content(clean_content)
                cursor = conn.execute("SELECT id FROM memories WHERE content_hash = ?", (c_hash,))
                if not cursor.fetchone():
                    vec = embed_text(clean_content)
                    insert_memory(conn, clean_content, vec, category=current_category)
                    inserted_count += 1

    return inserted_count
