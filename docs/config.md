# Configuration Reference

Configuration is split into two layers:

- **Workflow config** (`config/default.yaml`) — video processing, VLM, and agent settings. Loaded by the API and all workers. Each project gets its own copy at `{project}/config.yaml`, which overrides the default.
- **Runtime config** (`AppSettings`) — infrastructure settings loaded from environment variables only. Not stored in YAML.

---

## Hierarchy

```
Settings model defaults
    ↓ overridden by
config/default.yaml
    ↓ overridden by
{project}/config.yaml          (per-project copy)
```

Environment variables apply only to `AppSettings` (storage, Redis, config path).

---

## Runtime settings (environment variables)

| Variable | Type | Default | Description |
|---|---|---|---|
| `STORAGE_BACKEND` | str | `"local"` | Storage backend. Only `local` is implemented. |
| `STORAGE_ROOT` | path | `local/data/projects` | Root directory for all project data |
| `REDIS_URL` | str | `redis://localhost:6379/0` | Celery broker and result backend |
| `CONFIG_PATH` | path | `config/default.yaml` | Path to the default workflow config file |
| `HOST_STORAGE_ROOT` | str | — | Absolute host path to the projects folder. Used to generate `file://` URLs in `.otio` exports so NLEs can resolve source clips. **Required for export.** |
| `GEMINI_API_KEY` | str | — | Gemini API key for VLM descriptions |
| `MISTRAL_API_KEY` | str | — | Mistral API key (storyboard/editor agents) |
| `ANTHROPIC_API_KEY` | str | — | Anthropic API key |
| `OPENAI_API_KEY` | str | — | OpenAI API key |
| `LANGFUSE_PUBLIC_KEY` | str | — | Langfuse public key (optional tracing) |
| `LANGFUSE_SECRET_KEY` | str | — | Langfuse secret key (optional tracing) |
| `LANGFUSE_BASE_URL` | str | — | Langfuse endpoint. Leave unset to disable tracing. |
| `CELERY_VIDEO_CONCURRENCY` | int | `2` | Worker concurrency for the `video` queue |
| `CELERY_VLM_CONCURRENCY` | int | `10` | Worker concurrency for the `vlm` queue (gevent) |
| `CELERY_AGENTS_CONCURRENCY` | int | `2` | Worker concurrency for the `agents` queue |

---

## Workflow config (`config/default.yaml`)

### `video`

#### `video.downsample`

Controls how raw footage is scaled before analysis. Processing runs on the downsampled copy; the original is never modified.

| Field | Type | Default | Description |
|---|---|---|---|
| `target_fps` | float \| null | `null` | Target frame rate for the downsampled video. `null` preserves the source fps. |
| `target_width` | int | `640` | Target width in pixels. Height is scaled proportionally. |
| `output_format` | str | `"mp4"` | Container format for the downsampled output. |

#### `video.optical_flow`

Parameters for Farneback dense optical flow (OpenCV). These control the quality/speed tradeoff of motion estimation.

| Field | Type | Default | Description |
|---|---|---|---|
| `target_fps` | float | `4.0` | Frame rate at which frames are sampled for flow computation. Lower = faster, less precise. |
| `pyr_scale` | float | `0.5` | Image pyramid scale factor between levels (0–1). |
| `levels` | int | `3` | Number of pyramid levels. More levels = captures larger motions. |
| `winsize` | int | `15` | Averaging window size for flow estimation. Larger = smoother but blurs fine detail. |
| `iterations` | int | `3` | Number of solver iterations at each pyramid level. |
| `poly_n` | int | `5` | Size of the pixel neighborhood for polynomial expansion. |
| `poly_sigma` | float | `1.2` | Gaussian sigma for polynomial expansion smoothing. |

#### `video.segmentation`

Controls how optical flow signals are smoothed and where scene boundaries are placed.

| Field | Type | Default | Description |
|---|---|---|---|
| `fd_penalty` | float | `3.0` | PELT L2 penalty for coarse scene boundary detection. **Higher → fewer, longer segments. Lower → more, shorter segments.** This is the primary tuning knob. |
| `subseg_penalty` | float | `2.0` | PELT L1 penalty for camera-movement sub-segmentation within each scene. |
| `savgol_window` | int | `11` | Savitzky-Golay smoothing window (must be odd). Larger = smoother signal, fewer spurious boundaries. |
| `savgol_poly` | int | `2` | Savitzky-Golay polynomial order. |

#### `video` root

| Field | Type | Default | Description |
|---|---|---|---|
| `hwaccel` | str \| null | `null` | FFmpeg hardware acceleration backend. Examples: `"videotoolbox"` (macOS), `"cuda"` (NVIDIA), `"vaapi"` (Linux Intel/AMD). `null` uses software decoding. |

---

### `vlm`

Controls how segments are described by the Vision Language Model.

| Field | Type | Default | Description |
|---|---|---|---|
| `provider` | str | `"gemini"` | VLM provider. Only `gemini` is currently supported. |
| `model` | str | `"gemini-2.0-flash"` | Gemini model identifier. |
| `temperature` | float | `0.3` | Sampling temperature (0–1). Lower = more deterministic descriptions. |
| `gemini_api_key` | str \| null | `null` | Override the `GEMINI_API_KEY` env var per-project. |
| `request_delay_s` | float | `2.0` | Seconds to pause between segment VLM calls (CLI / VLMStep only). |
| `segment_rate_limit` | str | `"30/m"` | Celery rate limit applied to each `vlm.segment` task. |

---

### `storyboard`

Controls the storyboard generation LangGraph workflow.

| Field | Type | Default | Description |
|---|---|---|---|
| `max_revisions` | int | `2` | Maximum revision rounds before the agent accepts its best result. |
| `review_threshold` | float | `0.7` | Minimum score for a story to be approved without revision (0–1). |
| `context_threshold` | float | `0.5` | Hard floor for `context_adherence` score. Below this, the story is always sent for revision regardless of total score. |
| `human_in_the_loop` | bool | `false` | Insert a human review gate before the director step. Can also be set per-trigger via the API. |

#### Agent LLM configs

Each agent role has its own LLM config nested under `storyboard`:

| Key | Role | Default temperature |
|---|---|---|
| `story_writer` | Writes the initial narrative | `0.7` |
| `story_judge` | Validates narrative coherence | `0.1` |
| `narrator` | Enhances the story | `0.3` |
| `director` | Selects shots per scene | `0.5` |
| `judge` | Final quality scoring | `0.1` |

Each agent config (`AgentLLMConfig`) accepts:

| Field | Type | Default | Description |
|---|---|---|---|
| `provider` | str | `"mistral"` | LLM provider: `mistral`, `anthropic`, `openai`, `vllm` |
| `model` | str | `"mistral-large-latest"` | Model identifier |
| `temperature` | float | — | Sampling temperature |
| `base_url` | str \| null | `null` | Required for `mistral` and `vllm` providers. |
| `api_key` | str \| null | `null` | Override the provider env var key per-agent. |
| `extra_headers` | dict | `{}` | Additional HTTP headers (e.g., auth tokens for self-hosted models). |

---

### `editor`

Controls the timeline assembly LangGraph workflow.

#### Retrieval

| Field | Type | Default | Description |
|---|---|---|---|
| `embedding_model` | str | `"sentence-transformers/all-MiniLM-L6-v2"` | Sentence transformer model used to embed segment descriptions for FAISS retrieval. |
| `top_k_candidates` | int | `15` | Candidate segments retrieved per storyboard scene. |
| `min_candidates_per_scene` | int | `3` | Minimum candidates returned even if retrieval scores are low. |
| `candidate_alpha` | float | `0.7` | Blend weight between embedding score (alpha) and keyword score (1-alpha). Range 0–1. |

#### Chain selection

| Field | Type | Default | Description |
|---|---|---|---|
| `top_k_chains` | int | `5` | Top-k clip chains offered to the editorial selector agent per scene. |
| `duration_tolerance` | float | `0.2` | ±fraction of ideal duration used to filter candidate chains. E.g. `0.2` = ±20%. |

#### Stitching

| Field | Type | Default | Description |
|---|---|---|---|
| `stitching_cost_threshold` | float | `0.6` | Kinematic cost above which a scene boundary is flagged for the stitching agent. |
| `skip_stitching` | bool | `false` | Skip the `stitch_scenes` node entirely. |
| `skip_review` | bool | `false` | Skip the `review_timeline` node entirely. |

#### Cost function weights

Weights for the transition cost function used during chain assembly. They are applied together and should sum to a meaningful total (they are not normalized automatically).

| Field | Type | Default | Description |
|---|---|---|---|
| `w1` | float | `0.4` | Kinematic direction cost — penalizes reversals in pan/tilt/zoom direction. |
| `w2` | float | `0.3` | Kinematic magnitude ratio cost — penalizes abrupt speed changes. |
| `w3` | float | `0.2` | Instability penalty — penalizes high acceleration variance (`std_deriv`). |
| `w4` | float | `0.1` | Monotonicity reward — rewards smooth, consistent camera movement. |
| `w5` | float | `0.3` | Narrative mismatch penalty — penalizes clips that contradict the scene description. |

#### Human gates

| Field | Type | Default | Description |
|---|---|---|---|
| `human_in_the_loop` | bool | `false` | Enable human review gates. Can also be set per-trigger via the API. |
| `max_gate2_rounds` | int | `2` | Maximum rounds at Gate 2 (scene-level clip review) before the agent proceeds. |

#### Agent LLM configs

| Key | Role | Default temperature |
|---|---|---|
| `narrative_analyst` | Analyses the storyboard brief | `0.3` |
| `editorial_selector` | Selects and orders clip chains | `0.2` |
| `stitching_agent` | Plans transitions at flagged boundaries | `0.2` |
| `reviewer` | Final timeline quality check | `0.1` |

Each agent config follows the same `AgentLLMConfig` structure described under `storyboard`.

---

## Per-project config override

When a project is created, a copy of `config/default.yaml` is written to `{project}/config.yaml`. Edit that file to tune settings for a specific project without affecting others.

Example — increase segmentation granularity for a specific project:

```yaml
video:
  segmentation:
    fd_penalty: 1.5    # more, shorter segments
    subseg_penalty: 1.0
```

The config hash (`sha256` of the `video` section) is stored in the manifest. If it changes after a video has been processed, the pipeline will re-run segmentation automatically on the next upload or trigger.
