# AGENTS.md — ai-video-cutter

Reference for AI agents working in this codebase.

---

## What this project does

**ai-video-cutter** is an automated video editing system. It takes raw footage and produces a polished edit as an OpenTimelineIO (`.otio`) file ready for any NLE (DaVinci Resolve, Premiere Pro, Final Cut Pro X).

The pipeline:

```
Raw footage
    │
    ▼
Video Pipeline       — downsample → optical flow → scene segmentation → VLM descriptions
    │
    ▼
Storyboard Agent     — story writer → narrative judge → director (multi-agent, LangGraph)
    │
    ▼
Editor Agent         — embedding index → clip selection → assembly → review (multi-agent, LangGraph)
    │
    ▼
Export (.otio)       — file readable by any professional NLE
```

---

## Repository layout

```
src/
  api/          FastAPI app, route handlers, schemas
  core/         Storage, config loading, shared utilities
  video/        Video processing pipeline (downsample, optical flow, segmentation, VLM)
  storyboard/   LangGraph storyboard agent (graph.py, nodes.py, state.py, llm.py)
  editor/       LangGraph editor/timeline agent (graph.py, nodes.py, state.py, tools/)
  worker/       Celery task definitions and worker pool setup
config/
  default.yaml  Workflow configuration defaults
docs/
  api.md        Full REST API reference
  config.md     Full configuration reference
frontend/       React + Vite + Zustand + Tailwind UI (CapCut-style timeline editor)
cli.py          CLI entry point (bypasses the web stack)
```

---

## Architecture

### Services

| Service | Port | Role |
|---|---|---|
| `api` | 8000 | FastAPI, 2 workers. All REST endpoints. |
| `frontend` | 3001 | nginx serving the compiled React app. |
| `redis` | 6380 | Celery broker + result backend. |
| `celery-video` | — | CPU-bound video processing queue. |
| `celery-vlm` | — | I/O-bound VLM queue (gevent). |
| `celery-agents` | — | LLM agent queue. |
| `flower` | 5555 | Celery task monitor UI. |

All services are defined in `docker-compose.yml`. Start with `./start.sh`.

### Celery queues

Three separate worker pools run concurrently so no work type blocks another:

- **`video`** — CPU-heavy ffmpeg, OpenCV, optical flow, segmentation
- **`vlm`** — Gemini API calls for segment descriptions (gevent I/O)
- **`agents`** — LangGraph storyboard and editor runs

### Agents (LangGraph)

Both the storyboard and editor agents are implemented as LangGraph state machines:

- **Storyboard** (`src/storyboard/`): `story_writer → story_judge → director`. The judge can cycle the writer up to N revision rounds before approving.
- **Editor** (`src/editor/`): `indexer → scene_selector → assembler → stitch_reviewer`. Uses embedding search over VLM segment descriptions to match scenes from the storyboard to real clips.

Both agents support **human-in-the-loop** gates: pass `"human_in_the_loop": true` to the trigger endpoint, and the agent pauses at a review checkpoint (`status: "awaiting_human"`). Resume via the `/resume` endpoint with optional feedback or override decisions.

### Configuration layers

```
Settings model defaults
    ↓
config/default.yaml        — workflow defaults checked into the repo
    ↓
{project}/config.yaml      — per-project overrides (auto-created on project creation)
```

Runtime infrastructure (Redis URL, storage root, API keys) is set via environment variables only (not YAML). See `docs/config.md` for the full reference.

---

## Key data flow

1. **Upload video** → `POST /api/v1/projects/{name}/videos` → Celery `video` queue runs downsample → optical flow → segmentation → VLM describe → writes segment JSON to `local/data/projects/{name}/{video_hash}/`.

2. **Generate storyboard** → `POST /api/v1/projects/{name}/storyboard` with a narrative `brief` → Celery `agents` queue runs the LangGraph storyboard graph → writes `storyboard_v{N}.json`.

3. **Assemble timeline** → `POST /api/v1/projects/{name}/editor` → Celery `agents` queue runs the LangGraph editor graph → writes `timeline_v{N}.json`.

4. **Export** → `POST /api/v1/projects/{name}/export` → synchronous, writes `export_timeline/latest.otio`. Source clips are referenced as `file://` URLs resolved from `HOST_STORAGE_ROOT`.

---

## API conventions

- All project endpoints: `/api/v1/projects/{project_name}/...`
- Agent triggers return `202` with `{ task_id }`. Poll `GET /api/v1/status/{task_id}` for completion.
- Task states: `PENDING` → `STARTED` → `SUCCESS` | `FAILURE` | `awaiting_human`
- Project names: alphanumeric, underscores, hyphens only.
- Full endpoint reference: [docs/api.md](docs/api.md)

---

## Deployment

### Prerequisites

- Docker and Docker Compose v2
- API keys (see Environment variables below)

### Steps

```bash
# 1. Clone and enter the repo
git clone <repo-url>
cd ai-video-cutter

# 2. Create .env
cp .env.example .env
# Edit .env — fill in GEMINI_API_KEY, at least one LLM key, and HOST_STORAGE_ROOT

# 3. Start all services (detached)
./start.sh
```

`./start.sh` verifies `.env` exists, creates `local/data/projects/`, then runs `docker compose up --build -d`.

### Verify the stack is up

```bash
# API health check
curl http://localhost:8000/health
# → {"status": "ok"}

# List projects (empty on first run)
curl http://localhost:8000/api/v1/projects
# → []
```

Interactive API docs are at `http://localhost:8000/docs`.

### Endpoints an agent needs

The API is the only entry point. The agent should call `http://localhost:8000` (or whatever host/port the stack is deployed on). All paths are under `/api/v1/`.

**Minimum happy-path sequence:**

```
POST /api/v1/projects                          — create project
POST /api/v1/projects/{name}/videos            — upload video (multipart), triggers processing
GET  /api/v1/status/{task_id}                  — poll until celery_state == "SUCCESS"
POST /api/v1/projects/{name}/storyboard        — start storyboard agent (needs brief)
GET  /api/v1/status/{task_id}                  — poll until SUCCESS
POST /api/v1/projects/{name}/editor            — start editor agent
GET  /api/v1/status/{task_id}                  — poll until SUCCESS
POST /api/v1/projects/{name}/export            — export to .otio (synchronous)
```

### Polling pattern

Agent triggers are async. Always poll after triggering:

```python
import time, requests

BASE = "http://localhost:8000"

def wait_for_task(task_id, interval=5, timeout=600):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.get(f"{BASE}/api/v1/status/{task_id}").json()
        status = r["status"]
        if status == "SUCCESS":
            return r["result"]
        if status == "FAILURE":
            raise RuntimeError(r["error"])
        if status == "awaiting_human":
            raise RuntimeError("Task paused at human gate — resume via /resume endpoint")
        time.sleep(interval)
    raise TimeoutError(f"Task {task_id} did not complete within {timeout}s")
```

### Uploading a video

```python
with open("clip.mp4", "rb") as f:
    r = requests.post(
        f"{BASE}/api/v1/projects/my-project/videos",
        files={"file": ("clip.mp4", f, "video/mp4")},
        params={"include_vlm": True},
    )
task_id = r.json()["task_id"]
wait_for_task(task_id)
```

Upload is idempotent — re-uploading the same file reuses existing data.

### Generating a storyboard

```python
r = requests.post(
    f"{BASE}/api/v1/projects/my-project/storyboard",
    json={"brief": "A dramatic alpine journey building to a summit reveal.", "human_in_the_loop": False},
)
wait_for_task(r.json()["task_id"])
```

### Assembling a timeline

```python
r = requests.post(
    f"{BASE}/api/v1/projects/my-project/editor",
    json={"human_in_the_loop": False},
)
wait_for_task(r.json()["task_id"])
```

### Exporting

```python
r = requests.post(
    f"{BASE}/api/v1/projects/my-project/export",
    json={"version": "latest", "rate": 30.0},
)
otio_url = r.json()["otio_url"]   # file served at /files/...
```

### Stopping / restarting

```bash
docker compose down          # stop, keep volumes
docker compose down -v       # stop and delete redis data
./start.sh                   # restart
```

### Logs

```bash
docker compose logs -f api
docker compose logs -f celery-video
docker compose logs -f celery-agents
```

---

## CLI (no Docker required)

```bash
pip install -e ".[api,worker]"

python cli.py create my-project
python cli.py process my-project path/to/video.mp4 --describe
python cli.py storyboard my-project
python cli.py edit my-project
python cli.py export my-project
```

The CLI runs pipeline steps in-process without Celery or Redis.

---

## Environment variables (required)

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY` | VLM segment descriptions |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `MISTRAL_API_KEY` | LLM agents (at least one required) |
| `HOST_STORAGE_ROOT` | Absolute host path for `file://` URLs in `.otio` exports |

Copy `.env.example` to `.env` and fill in values before starting.

---

## Common tuning knobs

| Config key | Effect |
|---|---|
| `video.segmentation.fd_penalty` | Higher → fewer, longer segments. Lower → more, shorter segments. Primary tuning knob for cut frequency. |
| `video.downsample.target_width` | Lower → faster processing, less detail for VLM |
| `vlm.model` | Gemini model for segment descriptions |
| `storyboard.agents.*.model` | LLM model per storyboard agent role |
| `editor.agents.*.model` | LLM model per editor agent role |

Full reference: [docs/config.md](docs/config.md)

---

## Where to look for things

| Question | Where to look |
|---|---|
| How is a video segmented? | `src/video/segmentation.py`, `src/video/optical_flow.py` |
| How do VLM descriptions work? | `src/video/vlm.py`, `src/video/vlm_backend.py` |
| Storyboard agent logic | `src/storyboard/graph.py`, `src/storyboard/nodes.py` |
| Editor clip selection / cost model | `src/editor/nodes.py`, `src/editor/tools/` |
| API route definitions | `src/api/` |
| Celery task definitions | `src/worker/` |
| Default config values | `config/default.yaml` |
| Data schema types | `src/core/` and `docs/api.md` (Schemas section) |
