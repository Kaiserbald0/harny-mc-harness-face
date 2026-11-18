# HarnyMcHarnessFace

An autonomous LLM coding harness: give it a spec, it plans, implements, verifies, and opens a pull request — with a small API + UI to browse runs.

## Run

```bash
# setup (once)
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # fill in LLM_API_ENDPOINT / LLM_API_KEY / model choices

# pipeline (edit SPEC in main.py first)
.venv/bin/python main.py

# runs API
.venv/bin/uvicorn api.main:app --reload --port 8765

# UI
cd ui && npm install && npm run dev
```

---
<sup>Licensed under the [MIT License](LICENSE.md).</sup>
