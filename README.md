# agent-ecosystem-ng

An extensible AI multi-agent ecosystem built on JSON-RPC and MCP (Multi-Agent Communication Protocol). Each agent is a standalone MCP server communicating over JSON-RPC.

## Components

- **Need Agent** (`need_worker.py`): Collects and lists entity needs.
- **Opportunity Agent** (`opportunity_agent.py`): Receives and catalogs merchant offers.
- **Supplier Agent** (`supplier_agent.py`): Exposes supply catalog and delivery methods.
- **Merchant Agent** (`merchant_agent.py`): Syncs supply and publishes offers with markup.
- **Match Agent** (`match_agent.py`): Periodically matches needs and offers with pluggable scoring.
- **Insight Agent** (`insight_agent.py`): Generates predictions based on match outcomes.
- **Streamlit Dashboard** (`dashboard/streamlit_app.py`): Live UI for needs, offers, supply, matches, and predictions.

## Getting Started

1. **Clone** the repository (or rename your local project folder):
   ```bash
   git clone git@github.com:your-username/agent-ecosystem-ng.git
   cd agent-ecosystem-ng
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Launch with Docker Compose**:
   ```bash
   docker-compose up --build
   ```

4. **Access Services**:
   - Streamlit Dashboard: `http://localhost:8501`
   - Need Agent RPC: `http://localhost:9001/rpc`
   - Match Agent RPC: `http://localhost:9002/rpc`
   - Opportunity Agent RPC: `http://localhost:9003/rpc`
   - Merchant Agent RPC: `http://localhost:9004/rpc`
   - Supplier Agent RPC: `http://localhost:9005/rpc`
   - Insight Agent RPC: `http://localhost:9006/rpc`

## Renaming the GitHub Repo

If you’ve already pushed to GitHub, you can rename the remote and repository:

```bash
# On GitHub: rename the repo to 'agent-ecosystem-ng'
# Locally, update remote URL:
git remote set-url origin git@github.com:your-username/agent-ecosystem-ng.git
```

## License

MIT © Your Name
