#!/usr/bin/env python3
"""
ServiceNow → Markdown Database Sync
Pulls incidents, changes, problems, and knowledge articles
and writes them as structured Markdown files.
"""

import os
import sys
import json
import logging
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Config from environment ───────────────────────────────────────────────────
INSTANCE        = os.environ["SERVICENOW_INSTANCE"].rstrip("/")   # e.g. https://mycompany.service-now.com
USERNAME        = os.environ["SERVICENOW_USERNAME"]
PASSWORD        = os.environ["SERVICENOW_PASSWORD"]
CLIENT_ID       = os.environ.get("SERVICENOW_CLIENT_ID", "")
CLIENT_SECRET   = os.environ.get("SERVICENOW_CLIENT_SECRET", "")
SYNC_TYPE       = os.environ.get("SYNC_TYPE", "full")
LOOKBACK_HOURS  = int(os.environ.get("SYNC_LOOKBACK_HOURS", "8"))
MAX_RECORDS     = int(os.environ.get("MAX_RECORDS_PER_TABLE", "500"))

DB_ROOT = Path("database")

# ── ServiceNow Table Configs ──────────────────────────────────────────────────
TABLES = {
    "incidents": {
        "table":  "incident",
        "folder": DB_ROOT / "incidents",
        "prefix": "INC",
        "fields": [
            "number", "short_description", "description", "state",
            "priority", "urgency", "impact", "category", "subcategory",
            "assignment_group", "assigned_to", "caller_id",
            "opened_at", "resolved_at", "closed_at", "sys_updated_on",
            "close_notes", "work_notes", "cmdb_ci",
            "caused_by", "rfc", "problem_id",
        ],
        "filter": "active=true^ORstate=6^ORstate=7",
    },
    "changes": {
        "table":  "change_request",
        "folder": DB_ROOT / "changes",
        "prefix": "CHG",
        "fields": [
            "number", "short_description", "description", "state",
            "type", "risk", "impact", "priority",
            "assignment_group", "assigned_to", "requested_by",
            "start_date", "end_date", "sys_updated_on",
            "implementation_plan", "test_plan", "backout_plan",
            "justification", "close_notes", "cmdb_ci",
        ],
        "filter": "state!=0",
    },
    "problems": {
        "table":  "problem",
        "folder": DB_ROOT / "problems",
        "prefix": "PRB",
        "fields": [
            "number", "short_description", "description", "state",
            "priority", "assignment_group", "assigned_to",
            "opened_at", "sys_updated_on",
            "cause_notes", "fix_notes", "workaround", "known_error",
            "first_reported_by_task",
        ],
        "filter": "state!=4",
    },
    "knowledge": {
        "table":  "kb_knowledge",
        "folder": DB_ROOT / "knowledge",
        "prefix": "KB",
        "fields": [
            "number", "short_description", "text", "category",
            "author", "sys_updated_on", "valid_to",
            "kb_knowledge_base", "workflow_state",
        ],
        "filter": "workflow_state=published",
    },
}


# ── Auth ──────────────────────────────────────────────────────────────────────
def get_session() -> requests.Session:
    session = requests.Session()
    if CLIENT_ID and CLIENT_SECRET:
        log.info("Authenticating via OAuth2...")
        token_url = f"{INSTANCE}/oauth_token.do"
        resp = session.post(token_url, data={
            "grant_type":    "password",
            "client_id":     CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "username":      USERNAME,
            "password":      PASSWORD,
        }, timeout=30)
        resp.raise_for_status()
        token = resp.json()["access_token"]
        session.headers["Authorization"] = f"Bearer {token}"
    else:
        log.info("Authenticating via Basic Auth...")
        session.auth = (USERNAME, PASSWORD)

    session.headers.update({
        "Accept":       "application/json",
        "Content-Type": "application/json",
    })
    return session


# ── Fetch Records ─────────────────────────────────────────────────────────────
def fetch_records(session: requests.Session, table_cfg: dict, lookback_hours: int) -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    query = f"{table_cfg['filter']}^sys_updated_on>={since}"

    url     = f"{INSTANCE}/api/now/table/{table_cfg['table']}"
    records = []
    offset  = 0
    limit   = 100

    while offset < MAX_RECORDS:
        resp = session.get(url, params={
            "sysparm_query":  query,
            "sysparm_fields": ",".join(table_cfg["fields"]),
            "sysparm_limit":  limit,
            "sysparm_offset": offset,
            "sysparm_display_value": "true",
        }, timeout=60)

        if resp.status_code == 404:
            log.warning(f"Table {table_cfg['table']} not found — skipping.")
            break
        resp.raise_for_status()

        batch = resp.json().get("result", [])
        if not batch:
            break

        records.extend(batch)
        log.info(f"  Fetched {len(records)} records so far...")
        offset += limit

        if len(batch) < limit:
            break

    return records


# ── Markdown Writers ──────────────────────────────────────────────────────────
def val(record: dict, field: str) -> str:
    """Safe value extractor."""
    v = record.get(field, "")
    if isinstance(v, dict):
        v = v.get("display_value", "")
    return str(v or "").strip()


def write_incident(record: dict, folder: Path) -> Path:
    number = val(record, "number") or "INC_UNKNOWN"
    path   = folder / f"{number}.md"
    state_map = {"1": "New", "2": "In Progress", "3": "On Hold",
                 "4": "Resolved", "5": "Closed", "6": "Canceled", "7": "Closed"}
    prio_map  = {"1": "🔴 Critical", "2": "🟠 High", "3": "🟡 Moderate",
                 "4": "🟢 Low", "5": "⚪ Planning"}

    content = f"""---
type: incident
number: {number}
state: {val(record, 'state')}
priority: {val(record, 'priority')}
category: {val(record, 'category')}
subcategory: {val(record, 'subcategory')}
assignment_group: {val(record, 'assignment_group')}
assigned_to: {val(record, 'assigned_to')}
caller: {val(record, 'caller_id')}
opened_at: {val(record, 'opened_at')}
resolved_at: {val(record, 'resolved_at')}
updated_at: {val(record, 'sys_updated_on')}
ci: {val(record, 'cmdb_ci')}
related_change: {val(record, 'rfc')}
related_problem: {val(record, 'problem_id')}
---

# {number}: {val(record, 'short_description')}

## Details
| Field | Value |
|-------|-------|
| **State** | {val(record, 'state')} |
| **Priority** | {val(record, 'priority')} |
| **Category** | {val(record, 'category')} / {val(record, 'subcategory')} |
| **Assigned To** | {val(record, 'assigned_to')} ({val(record, 'assignment_group')}) |
| **CI** | {val(record, 'cmdb_ci')} |
| **Opened** | {val(record, 'opened_at')} |
| **Resolved** | {val(record, 'resolved_at')} |

## Description
{val(record, 'description') or '_No description provided._'}

## Resolution Notes
{val(record, 'close_notes') or '_Not yet resolved._'}

## Work Notes
{val(record, 'work_notes') or '_No work notes._'}

## Related Records
- **Change Request:** {val(record, 'rfc') or 'None'}
- **Problem:** {val(record, 'problem_id') or 'None'}

---
_Last synced: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_
"""
    path.write_text(content, encoding="utf-8")
    return path


def write_change(record: dict, folder: Path) -> Path:
    number = val(record, "number") or "CHG_UNKNOWN"
    path   = folder / f"{number}.md"
    content = f"""---
type: change
number: {number}
state: {val(record, 'state')}
change_type: {val(record, 'type')}
risk: {val(record, 'risk')}
priority: {val(record, 'priority')}
assignment_group: {val(record, 'assignment_group')}
start_date: {val(record, 'start_date')}
end_date: {val(record, 'end_date')}
updated_at: {val(record, 'sys_updated_on')}
ci: {val(record, 'cmdb_ci')}
---

# {number}: {val(record, 'short_description')}

## Details
| Field | Value |
|-------|-------|
| **Type** | {val(record, 'type')} |
| **State** | {val(record, 'state')} |
| **Risk** | {val(record, 'risk')} |
| **Priority** | {val(record, 'priority')} |
| **Assigned To** | {val(record, 'assigned_to')} ({val(record, 'assignment_group')}) |
| **CI** | {val(record, 'cmdb_ci')} |
| **Schedule** | {val(record, 'start_date')} → {val(record, 'end_date')} |

## Description
{val(record, 'description') or '_No description provided._'}

## Justification
{val(record, 'justification') or '_No justification provided._'}

## Implementation Plan
{val(record, 'implementation_plan') or '_No implementation plan._'}

## Test Plan
{val(record, 'test_plan') or '_No test plan._'}

## Backout Plan
{val(record, 'backout_plan') or '_No backout plan._'}

## Close Notes
{val(record, 'close_notes') or '_Not yet closed._'}

---
_Last synced: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_
"""
    path.write_text(content, encoding="utf-8")
    return path


def write_problem(record: dict, folder: Path) -> Path:
    number = val(record, "number") or "PRB_UNKNOWN"
    path   = folder / f"{number}.md"
    known_error = "✅ Yes" if val(record, "known_error").lower() == "true" else "❌ No"
    content = f"""---
type: problem
number: {number}
state: {val(record, 'state')}
priority: {val(record, 'priority')}
known_error: {val(record, 'known_error')}
assignment_group: {val(record, 'assignment_group')}
opened_at: {val(record, 'opened_at')}
updated_at: {val(record, 'sys_updated_on')}
---

# {number}: {val(record, 'short_description')}

## Details
| Field | Value |
|-------|-------|
| **State** | {val(record, 'state')} |
| **Priority** | {val(record, 'priority')} |
| **Known Error** | {known_error} |
| **Assigned To** | {val(record, 'assigned_to')} ({val(record, 'assignment_group')}) |
| **Opened** | {val(record, 'opened_at')} |

## Description
{val(record, 'description') or '_No description provided._'}

## Root Cause
{val(record, 'cause_notes') or '_Root cause under investigation._'}

## Workaround
{val(record, 'workaround') or '_No workaround available._'}

## Fix Notes
{val(record, 'fix_notes') or '_Not yet fixed._'}

---
_Last synced: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_
"""
    path.write_text(content, encoding="utf-8")
    return path


def write_knowledge(record: dict, folder: Path) -> Path:
    number = val(record, "number") or "KB_UNKNOWN"
    path   = folder / f"{number}.md"

    # Strip HTML tags simply (full HTML parser not needed for basic articles)
    import re
    body = val(record, "text")
    body = re.sub(r"<[^>]+>", "", body)  # strip HTML tags
    body = re.sub(r"\n{3,}", "\n\n", body).strip()

    valid_to = val(record, "valid_to")
    expiry_warning = ""
    if valid_to:
        try:
            exp = datetime.strptime(valid_to, "%Y-%m-%d %H:%M:%S")
            if exp < datetime.now():
                expiry_warning = f"\n> ⚠️ **WARNING:** This article expired on {valid_to}. Verify with owner before following.\n"
        except ValueError:
            pass

    content = f"""---
type: knowledge
number: {number}
category: {val(record, 'category')}
kb_base: {val(record, 'kb_knowledge_base')}
author: {val(record, 'author')}
valid_to: {valid_to}
updated_at: {val(record, 'sys_updated_on')}
state: {val(record, 'workflow_state')}
---

# {number}: {val(record, 'short_description')}
{expiry_warning}
## Article Info
| Field | Value |
|-------|-------|
| **Category** | {val(record, 'category')} |
| **Knowledge Base** | {val(record, 'kb_knowledge_base')} |
| **Author** | {val(record, 'author')} |
| **Valid To** | {valid_to or 'No expiry'} |
| **Last Updated** | {val(record, 'sys_updated_on')} |

## Content

{body or '_No content available._'}

---
_Last synced: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_
"""
    path.write_text(content, encoding="utf-8")
    return path


WRITERS = {
    "incidents": write_incident,
    "changes":   write_change,
    "problems":  write_problem,
    "knowledge": write_knowledge,
}


# ── Main ──────────────────────────────────────────────────────────────────────
def sync_table(session: requests.Session, name: str, cfg: dict) -> int:
    log.info(f"📥 Syncing {name}...")
    cfg["folder"].mkdir(parents=True, exist_ok=True)

    try:
        records = fetch_records(session, cfg, LOOKBACK_HOURS)
    except requests.HTTPError as e:
        log.error(f"Failed to fetch {name}: {e}")
        return 0

    writer = WRITERS[name]
    count  = 0
    for record in records:
        try:
            path = writer(record, cfg["folder"])
            count += 1
            log.debug(f"  ✍️  {path.name}")
        except Exception as e:
            log.warning(f"  ⚠️ Error writing record: {e}")

    log.info(f"  ✅ {count} {name} written.")
    return count


def main():
    log.info("🚀 ServiceNow sync starting...")
    log.info(f"   Instance    : {INSTANCE}")
    log.info(f"   Sync type   : {SYNC_TYPE}")
    log.info(f"   Lookback    : {LOOKBACK_HOURS}h")
    log.info(f"   Max records : {MAX_RECORDS}")

    session = get_session()

    tables_to_sync = (
        TABLES if SYNC_TYPE == "full" else {SYNC_TYPE: TABLES[SYNC_TYPE]}
    )

    totals = {}
    for name, cfg in tables_to_sync.items():
        totals[name] = sync_table(session, name, cfg)

    # Write sync manifest
    manifest = {
        "last_sync":    datetime.now(timezone.utc).isoformat(),
        "sync_type":    SYNC_TYPE,
        "lookback_h":   LOOKBACK_HOURS,
        "records_sync": totals,
    }
    (DB_ROOT / "sync_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    log.info("🎉 Sync complete.")
    log.info(f"   Summary: {totals}")


if __name__ == "__main__":
    main()
