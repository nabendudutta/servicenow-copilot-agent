#!/usr/bin/env python3
"""
Local test runner — loads .env and runs both sync + index build.
Usage:  python scripts/run_local.py [full|incidents|changes|problems|knowledge]
"""

import sys
import os
from pathlib import Path

# Load .env for local development
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(env_path)
    print(f"✅ Loaded environment from {env_path}")
else:
    print("⚠️  No .env file found. Using system environment variables.")

# Set defaults for local run
os.environ.setdefault("SYNC_TYPE",              sys.argv[1] if len(sys.argv) > 1 else "full")
os.environ.setdefault("SYNC_LOOKBACK_HOURS",    "24")   # 24h for first local run
os.environ.setdefault("MAX_RECORDS_PER_TABLE",  "50")   # small batch for testing

# Run sync
import sync_servicenow
sync_servicenow.main()

# Rebuild index
import build_index
build_index.build_index()

print("\n✅ Local sync complete. Check the database/ folder.")
