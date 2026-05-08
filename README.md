# 🤖 ServiceNow Copilot Agent

A GitHub Copilot custom agent that answers DevOps questions by reading a live Markdown database synced from ServiceNow — three times daily via GitHub Actions.

```
┌─────────────────────────────────────────────────────────┐
│  VS Code  ──►  GitHub Copilot  ──►  ServiceNow Copilot  │
│                     Agent                               │
│                       │                                 │
│              ┌────────▼────────┐                        │
│              │  database/ (MD) │  ◄──  ServiceNow API   │
│              │  index.md       │       (synced 3x/day)  │
│              │  query_cache.md │                        │
│              └─────────────────┘                        │
└─────────────────────────────────────────────────────────┘
```

---

## 📁 Repository Structure

```
servicenow-copilot-agent/
├── .copilot/
│   ├── agents.yml          ← Agent registration (name, model, instructions)
│   └── instructions.md     ← Agent behaviour & domain knowledge
│
├── .github/
│   └── workflows/
│       └── sync-servicenow.yml  ← Runs 3× daily (06:00, 14:00, 22:00 UTC)
│
├── scripts/
│   ├── sync_servicenow.py  ← Pulls data from ServiceNow REST API → Markdown
│   ├── build_index.py      ← Rebuilds database/index.md after every sync
│   ├── run_local.py        ← Local test runner (loads .env)
│   └── requirements.txt
│
├── database/
│   ├── index.md            ← Master search index (auto-generated)
│   ├── query_cache.md      ← Agent learns here to reduce token usage
│   ├── sync_manifest.json  ← Sync metadata
│   ├── incidents/          ← INC*.md files
│   ├── changes/            ← CHG*.md files
│   ├── problems/           ← PRB*.md files
│   └── knowledge/          ← KB*.md files
│
├── .env.example            ← Copy to .env for local dev
└── README.md
```

---

## 🚀 Step-by-Step Setup

### Step 1 — Fork / Clone the Repository

```bash
git clone https://github.com/YOUR_ORG/servicenow-copilot-agent.git
cd servicenow-copilot-agent
```

### Step 2 — Create ServiceNow API User

In your ServiceNow instance:

1. Go to **User Administration → Users → New**
2. Create user: `github_copilot_sync`
3. Assign roles: `itil` (read incidents/changes/problems) + `kb_reader`
4. Note the username and password

**Optional — OAuth2 (recommended for production):**
1. Go to **System OAuth → Application Registry → New**
2. Create: "GitHub Copilot Sync" — type: OAuth API endpoint for external clients
3. Note the **Client ID** and **Client Secret**

### Step 3 — Add GitHub Secrets

In your GitHub repo: **Settings → Secrets and variables → Actions → New repository secret**

| Secret Name | Value |
|---|---|
| `SERVICENOW_INSTANCE` | `https://yourcompany.service-now.com` |
| `SERVICENOW_USERNAME` | `github_copilot_sync` |
| `SERVICENOW_PASSWORD` | `your_password` |
| `SERVICENOW_CLIENT_ID` | *(optional)* OAuth Client ID |
| `SERVICENOW_CLIENT_SECRET` | *(optional)* OAuth Client Secret |

### Step 4 — Trigger First Sync

```
GitHub → Actions → "ServiceNow Data Sync" → Run workflow → full
```

Watch the workflow run. After it completes, the `database/` folder will be populated with Markdown files.

### Step 5 — Enable GitHub Copilot Custom Agents

Make sure your GitHub Copilot subscription supports **Copilot Chat in VS Code** (Individual, Business, or Enterprise).

In VS Code:
1. Install the **GitHub Copilot** and **GitHub Copilot Chat** extensions
2. Sign in to your GitHub account
3. Open the repo folder: `File → Open Folder → servicenow-copilot-agent`

### Step 6 — Select the Agent in VS Code

1. Open **Copilot Chat** (`Ctrl+Shift+I` / `Cmd+Shift+I`)
2. Click the **agent selector** (@ icon or model selector at top of chat)
3. Select **"ServiceNow Copilot"**
4. Start asking questions!

---

## 💬 Example Queries

```
@ServiceNow Copilot What are the open high-priority incidents for GitHub Actions?

@ServiceNow Copilot How do I fix a Terraform state lock error?

@ServiceNow Copilot Show me all emergency changes scheduled this week.

@ServiceNow Copilot Is there a known error for SonarQube quality gate timeouts?

@ServiceNow Copilot What does Veracode policy compliance failure mean and how do I fix it?

@ServiceNow Copilot Tell me about INC0001234
```

---

## 🏗️ How It Works

### Data Sync (3× daily)
```
GitHub Actions (cron)
    │
    ▼
sync_servicenow.py
    ├── Authenticates (Basic or OAuth2)
    ├── Queries /api/now/table/incident
    ├── Queries /api/now/table/change_request
    ├── Queries /api/now/table/problem
    ├── Queries /api/now/table/kb_knowledge
    └── Writes structured .md files to database/
         │
         ▼
build_index.py
    └── Rebuilds database/index.md (keyword index for the agent)
         │
         ▼
git commit & push
```

### Agent Query Flow
```
User asks question
    │
    ▼
Agent reads database/index.md  ←── Keyword match
    │
    ├── Match found → reads specific MD file
    │       └── Answers with Internal confidence score
    │
    └── No match → checks query_cache.md
            │
            ├── Cache hit → returns cached answer
            │
            └── Cache miss → 🌐 Searches internet
                    └── Answers with Internet confidence score
```

---

## 🔧 Local Development & Testing

```bash
# 1. Install dependencies
pip install -r scripts/requirements.txt

# 2. Copy and fill in .env
cp .env.example .env
# Edit .env with your ServiceNow credentials

# 3. Run local sync (fetches last 24h, max 50 records per table)
cd scripts
python run_local.py

# Or sync a single table
python run_local.py incidents

# 4. Check output
ls ../database/incidents/
cat ../database/index.md
```

---

## ⚙️ Customising the Sync

Edit `.env` (local) or GitHub Secrets (CI) to tune:

| Variable | Default | Description |
|---|---|---|
| `SYNC_TYPE` | `full` | `full` or single table name |
| `SYNC_LOOKBACK_HOURS` | `8` | How far back to look for changes |
| `MAX_RECORDS_PER_TABLE` | `500` | Cap per table per run |

To change sync times, edit the cron schedule in `.github/workflows/sync-servicenow.yml`.

---

## 🛡️ Security Notes

- **Never commit `.env`** — it's in `.gitignore`
- Use GitHub Secrets for all credentials in CI
- The ServiceNow API user should have **read-only** ITIL role only
- Rotate credentials quarterly — document in KB articles via the agent itself

---

## 🤝 DevOps Domain Coverage

The agent has built-in expertise in:

| Tool | Capabilities |
|---|---|
| **GitHub / Actions** | Repos, PRs, workflows, secrets, branch policies |
| **SonarQube** | Quality gates, code smells, coverage, token rotation |
| **Veracode** | SAST/DAST, policy compliance, flaw remediation |
| **XL Release** | Release pipelines, gates, approvals |
| **XL Deploy** | Deployment packages, environments, rollbacks |
| **Terraform** | State management, modules, drift, lock errors |
| **AWS / Azure / GCP** | IAM, networking, compute, cost |
| **ServiceNow** | ITSM, CMDB, incident/change/problem management |
