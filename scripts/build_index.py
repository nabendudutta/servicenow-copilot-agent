#!/usr/bin/env python3
"""
Build Search Index
Scans all Markdown files in database/ and produces:
  - database/index.md   — human-readable, keyword-rich index (used by the agent)
  - database/query_cache.md — placeholder for agent-cached responses
"""

import json
import re
from pathlib import Path
from datetime import datetime, timezone

DB_ROOT = Path("database")

FOLDERS = {
    "incidents": DB_ROOT / "incidents",
    "changes":   DB_ROOT / "changes",
    "problems":  DB_ROOT / "problems",
    "knowledge": DB_ROOT / "knowledge",
}

EMOJI = {
    "incidents": "🚨",
    "changes":   "🔧",
    "problems":  "🐛",
    "knowledge": "📖",
}


def extract_frontmatter(text: str) -> dict:
    """Parse YAML-style frontmatter between --- delimiters."""
    meta = {}
    if not text.startswith("---"):
        return meta
    parts = text.split("---", 2)
    if len(parts) < 3:
        return meta
    for line in parts[1].splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
    return meta


def extract_keywords(text: str) -> list[str]:
    """Pull meaningful words as keywords (naive but fast)."""
    # Remove frontmatter and Markdown syntax
    clean = re.sub(r"---.*?---", "", text, flags=re.DOTALL)
    clean = re.sub(r"[#*`|_>\[\]()]", " ", clean)
    words = re.findall(r"\b[A-Za-z][A-Za-z0-9_\-]{3,}\b", clean)
    # Deduplicate and lowercase, drop common stop-ish words
    seen, result = set(), []
    stop = {"from", "with", "that", "this", "have", "will", "last", "date", "time",
            "none", "field", "value", "last", "notes", "true", "false"}
    for w in words:
        lw = w.lower()
        if lw not in seen and lw not in stop:
            seen.add(lw)
            result.append(lw)
    return result[:30]  # cap at 30 keywords per file


def build_index():
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Load sync manifest if present
    manifest_path = DB_ROOT / "sync_manifest.json"
    manifest = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())

    index_lines = [
        "# 🗄️ ServiceNow Copilot — Search Index",
        "",
        f"> **Last indexed:** {now_str}  ",
        f"> **Last sync:** {manifest.get('last_sync', 'Unknown')}  ",
        f"> **Records:** {manifest.get('records_sync', {})}",
        "",
        "---",
        "",
        "## How to use this index",
        "This file is the entry point for the ServiceNow Copilot agent.",
        "Each entry lists the record number, a short description, and searchable keywords.",
        "The agent matches your query keywords against this index to find relevant records.",
        "",
        "---",
        "",
    ]

    total = 0

    for section, folder in FOLDERS.items():
        emoji = EMOJI[section]
        files = sorted(folder.glob("*.md")) if folder.exists() else []
        count = len(files)
        total += count

        index_lines += [
            f"## {emoji} {section.capitalize()} ({count} records)",
            "",
            "| Number | Short Description | Keywords |",
            "|--------|-------------------|----------|",
        ]

        for md_file in files:
            text = md_file.read_text(encoding="utf-8", errors="ignore")
            meta = extract_frontmatter(text)
            kw   = extract_keywords(text)

            number = meta.get("number", md_file.stem)
            desc   = ""
            for line in text.splitlines():
                if line.startswith("# ") and ":" in line:
                    _, _, desc = line.partition(": ")
                    desc = desc.strip()[:80]
                    break

            kw_str = ", ".join(kw[:12])
            rel_path = f"{section}/{md_file.name}"
            index_lines.append(
                f"| [{number}]({rel_path}) | {desc or '_No description_'} | {kw_str} |"
            )

        index_lines += ["", ""]

    index_lines += [
        "---",
        f"*Total records indexed: **{total}** | Generated: {now_str}*",
    ]

    index_path = DB_ROOT / "index.md"
    index_path.write_text("\n".join(index_lines), encoding="utf-8")
    print(f"✅ Index written: {index_path} ({total} records)")

    # Create query cache file if it doesn't exist
    cache_path = DB_ROOT / "query_cache.md"
    if not cache_path.exists():
        cache_path.write_text(
            "# 🧠 Query Cache\n\n"
            "> This file is maintained by the ServiceNow Copilot agent.\n"
            "> Frequently asked questions and their answers are cached here\n"
            "> to reduce token usage and improve response speed.\n\n"
            "---\n\n"
            "_No cached queries yet._\n",
            encoding="utf-8",
        )
        print("✅ Query cache initialised.")


if __name__ == "__main__":
    DB_ROOT.mkdir(exist_ok=True)
    for folder in FOLDERS.values():
        folder.mkdir(parents=True, exist_ok=True)
    build_index()
