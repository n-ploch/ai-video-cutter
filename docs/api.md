# API Reference

Base URL: `http://localhost:8000`

All project endpoints are under `/api/v1/`. Interactive docs are available at `/docs` (Swagger UI) and `/redoc`.

---

## Common patterns

### Async task flow

Agent endpoints (storyboard, editor) run asynchronously via Celery. The response to a trigger is `202 Accepted` with a `task_id`. Poll for completion:

```
POST /api/v1/projects/{name}/storyboard  →  202 { task_id }
GET  /api/v1/status/{task_id}            →  { status: "STARTED" | "SUCCESS" | "FAILURE" }
```

### Human-in-the-loop gates

When `human_in_the_loop: true` is passed, the agent pauses at a review gate. The task enters `status: "awaiting_human"`. Resume with the `/resume` endpoint, optionally injecting feedback or decisions.

### Error codes

| Code | Meaning |
|---|---|
| 404 | Project or resource not found |
| 409 | Project already exists (on create) |
| 422 | Validation error — check request body |
| 409 | Agent already running (STARTED or RETRY state) |

---

## Health

### `GET /health`

Returns `{"status": "ok"}`. Used by Docker health checks.

---

## Projects

### `GET /api/v1/projects`

List all projects.

**Response `200`** — `list[ProjectResponse]`

```json
[
  {
    "id": "my-project",
    "name": "my-project",
    "status": "ready",
    "created_at": "2025-01-15T10:00:00Z",
    "video_count": 2,
    "has_storyboard": true,
    "has_timeline": false
  }
]
```

---

### `POST /api/v1/projects`

Create a new project.

**Request body**

```json
{ "name": "my-project" }
```

`name` — alphanumeric, underscores, and hyphens only.

**Response `201`** — `ProjectResponse`

**Error `409`** — project already exists.

---

### `GET /api/v1/projects/{project_name}`

Get detailed project status.

**Response `200`** — `ProjectDetailResponse`

```json
{
  "id": "my-project",
  "name": "my-project",
  "status": "ready",
  "created_at": "2025-01-15T10:00:00Z",
  "video_count": 1,
  "has_storyboard": true,
  "has_timeline": true,
  "videos": [ /* VideoProcessingStatus[] */ ],
  "storyboard": { /* AgentTaskStatus */ },
  "editor": { /* AgentTaskStatus */ },
  "config": { /* Settings dict */ }
}
```

---

### `DELETE /api/v1/projects/{project_name}`

Delete a project and all its data. Irreversible.

**Response `204`** — no content.

---

### `GET /api/v1/projects/{project_name}/config`

Get the merged configuration for a project (default + project overrides).

**Response `200`**

```json
{
  "config": { /* full Settings dict */ },
  "config_hash": "sha256hex..."
}
```

---

### `PATCH /api/v1/projects/{project_name}/config`

Partially update project configuration. The body is deep-merged into the current config.

**Request body** — partial `Settings` dict, e.g.:

```json
{
  "video": {
    "segmentation": { "fd_penalty": 1.5 }
  }
}
```

**Response `200`** — updated `ConfigResponse` (same shape as GET config).

---

## Videos

### `GET /api/v1/projects/{project_name}/videos`

List all videos in a project with their processing status.

**Response `200`** — `list[VideoProcessingStatus]`

```json
[
  {
    "video_hash": "6097dcad...",
    "filename": "clip01.mp4",
    "steps": {
      "downloaded":  "2025-01-15T10:01:00Z",
      "downsampled": "2025-01-15T10:02:00Z",
      "flow_computed": "2025-01-15T10:03:00Z",
      "segmented":   "2025-01-15T10:04:00Z",
      "described":   "2025-01-15T10:06:00Z"
    },
    "config_hash": "sha256hex...",
    "celery_task_id": "abc-123",
    "celery_state": "SUCCESS",
    "current_step": "described"
  }
]
```

`steps` values are ISO timestamps when the step completed, or `null` if not yet done.

---

### `GET /api/v1/projects/{project_name}/videos/{video_hash}/status`

Get processing status for a single video by its content hash.

**Response `200`** — `VideoProcessingStatus` (same shape as above).

---

### `POST /api/v1/projects/{project_name}/videos`

Upload a video and start the processing pipeline.

**Request** — `multipart/form-data`

| Field | Type | Required | Description |
|---|---|---|---|
| `file` | file | yes | Video file |

**Query params**

| Param | Type | Default | Description |
|---|---|---|---|
| `include_vlm` | bool | `true` | Include the VLM segment description step |

**Response `202`**

```json
{
  "video_hash": "6097dcad...",
  "filename": "clip01.mp4",
  "task_id": "abc-123",
  "status": "queued"
}
```

Upload is idempotent — uploading the same file twice reuses existing data and re-triggers only missing steps.

**Pipeline steps:**

```
downsample → flow + segment → [vlm describe]
```

---

## Storyboard

### `POST /api/v1/projects/{project_name}/storyboard`

Trigger the storyboard generation agent.

**Prerequisites:** All videos must be fully processed (including VLM descriptions). No storyboard task may be actively running.

**Request body**

```json
{
  "brief": "A dramatic journey through alpine wilderness, building to a triumphant summit reveal.",
  "human_in_the_loop": false
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `brief` | str | yes | Narrative brief for the story writer |
| `human_in_the_loop` | bool | no | Pause for human review before the director step |

**Response `202`** — `TaskResponse`

```json
{
  "task_id": "abc-123",
  "status": "PENDING",
  "result": null,
  "error": null
}
```

---

### `POST /api/v1/projects/{project_name}/storyboard/resume`

Resume a storyboard run paused at a human-review gate.

**Request body**

```json
{
  "thread_id": "langgraph-thread-id",
  "feedback": "Make the third scene more contemplative."
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `thread_id` | str | yes | LangGraph thread ID from the paused task result |
| `feedback` | str \| null | no | Revised brief injected before resuming |

**Response `202`** — `TaskResponse`

---

### `GET /api/v1/projects/{project_name}/storyboard`

Get the storyboard output.

**Query params**

| Param | Type | Default | Description |
|---|---|---|---|
| `version` | int | `null` | Specific version number. Omit for latest. |

**Response `200`** — `StoryboardOutput`

```json
{
  "user_brief": "A dramatic journey...",
  "story": "Full narrative text...",
  "narration_beats": [
    { "id": 1, "text": "The drone ascends from the gorge..." }
  ],
  "scenes": [
    {
      "id": 1,
      "narration_segment": "beat_1",
      "scene_description": "Wide establishing shot of alpine gorge",
      "reasoning": "Opens the visual journey with scale",
      "keywords": ["wide", "establishing", "alpine", "gorge"]
    }
  ],
  "story_judge_result": {
    "narrative_quality": 0.85,
    "brief_adherence": 0.90,
    "context_adherence": 0.80,
    "total_score": 0.85,
    "feedback": "Strong arc, good pacing.",
    "decision": "approve"
  },
  "story_revision_count": 1,
  "judge_result": {
    "score": 0.88,
    "feedback": "Excellent narrative coherence.",
    "decision": "approve"
  },
  "revision_count": 0
}
```

---

### `GET /api/v1/projects/{project_name}/storyboard/versions`

List all storyboard versions.

**Response `200`**

```json
[
  {
    "version": 1,
    "created_at": "2025-01-15T11:00:00Z",
    "brief_snippet": "A dramatic journey through alpine wilderness..."
  }
]
```

---

## Editor

### `POST /api/v1/projects/{project_name}/editor`

Trigger the timeline assembly agent.

**Prerequisites:** A storyboard must exist. All videos must be fully processed.

**Request body**

```json
{
  "human_in_the_loop": false,
  "storyboard_version": null
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `human_in_the_loop` | bool | no | Pause for human review at gate 2 (scene selection) |
| `storyboard_version` | int \| null | no | Specific storyboard version to use. `null` uses latest. |

**Response `202`** — `TaskResponse`

---

### `POST /api/v1/projects/{project_name}/editor/resume`

Resume an editor run paused at a human-review gate.

**Request body**

```json
{
  "thread_id": "langgraph-thread-id",
  "gate_overrides": {
    "gate2_overrides": {
      "scene_001": { "chain_index": 2 }
    },
    "flagged_scene_ids": ["scene_003"]
  }
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `thread_id` | str | yes | LangGraph thread ID from the paused task result |
| `gate_overrides` | dict | no | Per-scene decisions to inject |

**Response `202`** — `TaskResponse`

---

### `GET /api/v1/projects/{project_name}/editor`

Get the timeline output.

**Query params**

| Param | Type | Default | Description |
|---|---|---|---|
| `version` | int | `null` | Specific version number. Omit for latest. |

**Response `200`** — `TimelineOutput`

```json
{
  "project_name": "my-project",
  "scenes": [
    {
      "scene_id": 1,
      "scene_description": "Wide establishing shot of alpine gorge",
      "chain_cost": 0.32,
      "total_duration": 8.5,
      "entries": [
        {
          "position": 1,
          "scene_id": 1,
          "segment_id": "a1b2c3d4",
          "video_file": "clip01.mp4",
          "source_video": "6097dcad...",
          "start": 12.0,
          "end": 20.5,
          "duration": 8.5,
          "bucket_idx": 0,
          "quality_rating": "excellent",
          "edge_cost": 0.0,
          "stitch_action": "cut"
        }
      ]
    }
  ],
  "boundaries": [
    {
      "scene_id_a": 1,
      "scene_id_b": 2,
      "segment_id_a": "a1b2c3d4",
      "segment_id_b": "e5f6a7b8",
      "kinematic_cost": 0.71,
      "flagged": true
    }
  ],
  "stitch_decisions": [
    {
      "boundary_idx": 0,
      "action": "transition",
      "transition_type": "dissolve",
      "swap_segment_id": "",
      "reasoning": "Direction reversal — dissolve softens the cut."
    }
  ],
  "review": {
    "overall_score": 0.87,
    "has_structural_issues": false,
    "auto_fix_applied": [],
    "decision": "approve"
  },
  "approved": true,
  "total_duration": 47.3,
  "total_segments": 6
}
```

---

### `GET /api/v1/projects/{project_name}/editor/versions`

List all timeline versions.

**Response `200`**

```json
[
  {
    "version": 1,
    "created_at": "2025-01-15T12:00:00Z",
    "storyboard_version": 1,
    "brief_snippet": "A dramatic journey through alpine wilderness..."
  }
]
```

---

## Export

### `POST /api/v1/projects/{project_name}/export`

Export the timeline to OpenTimelineIO (`.otio`) format. Runs synchronously.

**Request body**

```json
{
  "version": "latest",
  "rate": 30.0
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `version` | str | `"latest"` | Timeline version to export: `"latest"` or `"v{N}"` (e.g. `"v2"`) |
| `rate` | float | `30.0` | Output frame rate for the OTIO timeline |

**Response `200`**

```json
{
  "version": "latest",
  "otio_url": "http://localhost:8000/files/my-project/export_timeline/latest.otio",
  "total_segments": 6,
  "total_duration": 47.3
}
```

The `.otio` file embeds `file://` source URLs derived from `HOST_STORAGE_ROOT`. Import it directly into DaVinci Resolve, Premiere Pro, or Final Cut Pro X.

---

## Status

### `GET /api/v1/status/{task_id}`

Get Celery task status for any task ID.

**Response `200`** — `TaskResponse`

```json
{
  "task_id": "abc-123",
  "status": "SUCCESS",
  "result": { /* task result dict */ },
  "error": null
}
```

**`status` values**

| Value | Meaning |
|---|---|
| `PENDING` | Task queued, not yet started |
| `STARTED` | Worker is executing |
| `SUCCESS` | Completed successfully |
| `FAILURE` | Failed — see `error` field |
| `RETRY` | Being retried after a transient error |
| `awaiting_human` | Paused at a human-review gate |

---

### `GET /api/v1/projects/{project_name}/status`

Unified status for a project: all videos, storyboard, and editor in one response.

**Response `200`** — `ProjectDetailResponse` (same as `GET /api/v1/projects/{project_name}`)

---

## Static files

### `GET /files/{path}`

Serves project data files directly from the local storage root. Used to stream `.otio` exports and other artifacts.

Example: `GET /files/my-project/export_timeline/latest.otio`

---

## Schemas

### `VideoProcessingStatus`

| Field | Type | Description |
|---|---|---|
| `video_hash` | str | SHA-256 content hash of the original file |
| `filename` | str | Original filename |
| `steps` | dict[str, str \| null] | Step name → ISO completion timestamp, or `null` |
| `config_hash` | str \| null | Config hash at upload time |
| `celery_task_id` | str \| null | Root Celery task ID |
| `celery_state` | str \| null | Celery task state |
| `current_step` | str \| null | Most informative current step for display |

**Step names:** `downloaded`, `downsampled`, `flow_computed`, `segmented`, `described`

---

### `TimelineSegmentEntry`

| Field | Type | Description |
|---|---|---|
| `position` | int | 1-based index in the final cut |
| `scene_id` | int | Parent scene ID |
| `segment_id` | str | 8-char deterministic hash |
| `video_file` | str | Original filename |
| `source_video` | str | Video content hash |
| `start` | float | Start time in seconds |
| `end` | float | End time in seconds |
| `duration` | float | Duration in seconds |
| `bucket_idx` | int | Narrative bucket index |
| `quality_rating` | str | `"excellent"` \| `"good"` \| `"medium"` \| `"bad"` |
| `edge_cost` | float | Transition cost into this segment |
| `stitch_action` | str | `"cut"` \| `"dissolve"` \| etc. |

---

### `CameraMovement`

Kinematic data per sub-segment, used for transition cost computation.

| Field | Type | Description |
|---|---|---|
| `movement_id` | int | Sub-segment index |
| `start_time` | float | Seconds |
| `end_time` | float | Seconds |
| `pan_entry_vel` | float | Pan velocity at entry |
| `tilt_entry_vel` | float | Tilt velocity at entry |
| `zoom_entry_vel` | float | Zoom velocity at entry |
| `pan_exit_vel` | float | Pan velocity at exit |
| `tilt_exit_vel` | float | Tilt velocity at exit |
| `zoom_exit_vel` | float | Zoom velocity at exit |
| `pan_monotonicity` | float | Directional consistency 0–1 |
| `tilt_monotonicity` | float | |
| `zoom_monotonicity` | float | |
| `pan_mean_abs_deriv` | float | Average acceleration magnitude |
| `tilt_mean_abs_deriv` | float | |
| `zoom_mean_abs_deriv` | float | |
| `pan_std_deriv` | float | Acceleration instability |
| `tilt_std_deriv` | float | |
| `zoom_std_deriv` | float | |
