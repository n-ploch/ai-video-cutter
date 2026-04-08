"""LangGraph node implementations for the timeline assembly agent."""
from __future__ import annotations

import json
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage

from core.prompts import (
    EDITORIAL_SELECTOR_PROMPT,
    NARRATIVE_ANALYST_PROMPT,
    REVIEWER_PROMPT,
    STITCHING_PROMPT,
)
from core.schemas.editor import (
    BoundaryInfo,
    Chain,
    ChainSelection,
    NarrativeAnalysis,
    StitchDecision,
    TimelineReview,
    TimelineSegmentEntry,
)
from editor.state import EditorState

log = logging.getLogger(__name__)


# ── helpers (mirrors storyboard/nodes.py) ─────────────────────────────────────

def _invoke(llm: BaseChatModel, prompt: str) -> str:
    response = llm.invoke([HumanMessage(content=prompt)])
    return response.content.strip()


def _parse_json(text: str) -> dict | list:
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return json.loads(text)


def _format_candidates(candidates: list[dict], segments_by_id: dict[str, dict]) -> str:
    lines: list[str] = []
    for c in candidates:
        seg = segments_by_id.get(c["segment_id"], {})
        vlm_list = seg.get("vlm", [])
        desc = vlm_list[0].get("description", "(no description)") if vlm_list else "(no description)"
        lines.append(
            f"{c['segment_id']} | {c['duration']:.1f}s | {c['quality_rating']} | {desc}"
        )
    return "\n".join(lines) if lines else "(none)"


def _format_chains(chains: list[dict], segments_by_id: dict[str, dict]) -> str:
    lines: list[str] = []
    for idx, chain in enumerate(chains):
        seg_summaries = []
        for link in chain.get("links", []):
            seg = segments_by_id.get(link["segment_id"], {})
            vlm_list = seg.get("vlm", [])
            desc = (vlm_list[0].get("description", "")[:60] if vlm_list else "")
            seg_summaries.append(f"[b{link['bucket_idx']}] {link['segment_id']} ({desc})")
        lines.append(
            f"{idx} | cost={chain['total_cost']:.3f} | {chain['total_duration']:.1f}s | "
            + " → ".join(seg_summaries)
        )
    return "\n".join(lines) if lines else "(no chains)"


def _format_swap_candidates(swap_ids: list[str], segments_by_id: dict[str, dict], predecessor_seg: dict) -> str:
    from editor.tools.stitching import compute_boundary_cost
    from core.config import EditorConfig
    lines: list[str] = []
    for sid in swap_ids:
        seg = segments_by_id.get(sid, {})
        vlm_list = seg.get("vlm", [])
        desc = (vlm_list[0].get("description", "")[:80] if vlm_list else "(no description)")
        lines.append(f"{sid} | — | {desc}")
    return "\n".join(lines) if lines else "(no swap candidates)"


def _get_selected_chain(state: EditorState, scene_id: int) -> dict | None:
    """Retrieve the selected chain dict for a scene from state."""
    sid = str(scene_id)
    selection = state["chain_selections"].get(sid)
    if selection is None:
        return None
    chains = state["chains_per_scene"].get(sid, [])
    idx = selection.get("selected_chain_index", 0)
    if idx < len(chains):
        return chains[idx]
    return chains[0] if chains else None


# ── Node: build embedding index ───────────────────────────────────────────────

def make_build_index_node(cfg):
    """Build the in-memory embedding index from all segments."""
    from editor.tools.embedding import build_segment_index

    def build_embedding_index_node(state: EditorState) -> dict:
        # Per-video segment counts
        counts: dict[str, int] = {}
        for seg in state["segments"]:
            vf = seg.get("video_file") or seg.get("source_video") or "unknown"
            counts[vf] = counts.get(vf, 0) + 1
        for vf, n in sorted(counts.items()):
            log.info("build_embedding_index: %s → %d segments", vf, n)
        log.info("build_embedding_index: encoding %d segments total", len(state["segments"]))
        build_segment_index(state["segments"], cfg.embedding_model)
        return {}

    return build_embedding_index_node


# ── Node: retrieve candidates ─────────────────────────────────────────────────

def make_retrieve_candidates_node(cfg):
    from editor.tools.embedding import get_index, retrieve_candidates

    def retrieve_candidates_node(state: EditorState) -> dict:
        matrix, ids = get_index()
        all_candidates: dict = {}
        for scene in state["scenes"]:
            sid = str(scene["id"])
            candidates = retrieve_candidates(scene, state["segments"], matrix, ids, cfg)
            all_candidates[sid] = [c.model_dump() for c in candidates]
            log.info(
                "retrieve_candidates: scene %s → %d candidates",
                sid, len(candidates),
            )
        return {"scene_candidates": all_candidates}

    return retrieve_candidates_node


# ── Node: deduplicate candidates ──────────────────────────────────────────────

def deduplicate_candidates_node(state: EditorState) -> dict:
    """Assign each segment to the scene where it has the highest combined_score."""
    # Invert: segment_id → [(scene_id_str, combined_score)]
    seg_to_scenes: dict[str, list[tuple[str, float]]] = {}
    for sid, candidates in state["scene_candidates"].items():
        for c in candidates:
            seg_to_scenes.setdefault(c["segment_id"], []).append((sid, c["combined_score"]))

    contested = sum(1 for v in seg_to_scenes.values() if len(v) > 1)
    log.info(
        "deduplicate: %d unique segments across %d scenes, %d contested",
        len(seg_to_scenes), len(state["scene_candidates"]), contested,
    )

    # For each segment in multiple pools, keep only the highest-scoring scene
    winner: dict[str, str] = {}
    for seg_id, scene_scores in seg_to_scenes.items():
        best_scene = max(scene_scores, key=lambda x: x[1])[0]
        winner[seg_id] = best_scene

    # Rebuild pools
    deduped: dict[str, list[dict]] = {sid: [] for sid in state["scene_candidates"]}
    for sid, candidates in state["scene_candidates"].items():
        before = len(candidates)
        for c in candidates:
            if winner.get(c["segment_id"]) == sid:
                deduped[sid].append(c)
        after = len(deduped[sid])
        log.info(
            "deduplicate: scene %s — kept %d/%d candidates (%d lost to other scenes)",
            sid, after, before, before - after,
        )

    # Gap warnings
    gap_warnings: list[str] = []
    for sid, pool in deduped.items():
        if len(pool) < state["min_candidates_per_scene"]:
            msg = (
                f"Scene {sid} has only {len(pool)} candidate(s) after deduplication "
                f"(minimum {state['min_candidates_per_scene']})"
            )
            log.warning("deduplicate: %s", msg)
            gap_warnings.append(msg)

    return {"deduped_candidates": deduped, "gap_warnings": gap_warnings}


# ── Node: dispatch scenes (updates gate2_round; routing fn does the fan-out) ──

def make_dispatch_scenes_node(cfg):
    """Return a node that increments gate2_round for re-assembly rounds.

    The actual fan-out to parallel ``assemble_scene`` nodes is performed by
    ``_fan_out_scenes`` (a routing function used with ``add_conditional_edges``
    in graph.py).  Keeping state updates and routing separate avoids mixing
    ``Send()`` objects with dict returns from the same node.
    """

    def dispatch_scenes_node(state: EditorState) -> dict:
        flagged = state.get("flagged_scene_ids") or []
        is_reassembly = bool(flagged) or (state.get("review") is not None)
        new_gate2_round = state["gate2_round"] + 1 if is_reassembly else state["gate2_round"]
        # Clear flagged_scene_ids here (single node, before parallel fan-out) so that
        # assemble_scene branches don't each try to write it concurrently.
        return {"gate2_round": new_gate2_round, "flagged_scene_ids": []}

    return dispatch_scenes_node


# ── Node: assemble one scene (Phases A + B + C) ───────────────────────────────

def make_assemble_scene_node(
    analyst_llm: BaseChatModel,
    selector_llm: BaseChatModel,
    cfg,
):
    """Return a node that assembles a single scene.

    Invoked via ``Send("assemble_scene", scene_state)`` from the routing
    function ``_fan_out_scenes`` in graph.py.  ``scene_state`` is a plain
    dict (not the full EditorState) containing:

        scene            — StoryboardScene dict for this scene
        segments_by_id   — {segment_id: segment dict}
        deduped_candidates — {str(scene_id): [CandidateInfo dicts]}
        gate2_overrides  — {str(scene_id): override dict}
        top_k_chains     — int

    Returns a partial state update that is merged into the full EditorState
    via the ``_merge_dict`` reducers on ``narrative_analyses``,
    ``chains_per_scene``, and ``chain_selections``.
    """
    structured_analyst = analyst_llm.with_structured_output(NarrativeAnalysis)
    structured_selector = selector_llm.with_structured_output(ChainSelection)

    from editor.tools.pathfinding import build_dag, find_chains

    def assemble_scene_node(scene_state: dict) -> dict:
        scene = scene_state["scene"]
        segments_by_id: dict[str, dict] = scene_state["segments_by_id"]
        deduped_candidates: dict = scene_state["deduped_candidates"]
        gate2_overrides: dict = scene_state.get("gate2_overrides") or {}
        top_k_chains: int = scene_state["top_k_chains"]

        sid = str(scene["id"])
        candidates = deduped_candidates.get(sid, [])

        log.info(
            "assemble_scene: scene %s — Phase A (narrative analysis, %d candidates)",
            sid, len(candidates),
        )

        # ── Phase A: Narrative analysis ───────────────────────────────────────
        candidate_list_text = _format_candidates(candidates, segments_by_id)
        phase_a_prompt = NARRATIVE_ANALYST_PROMPT.format(
            scene_id=scene["id"],
            narration_text=scene.get("narration_segment", ""),
            scene_description=scene.get("scene_description", ""),
            keywords=", ".join(scene.get("keywords", [])),
            candidate_list=candidate_list_text,
        )
        analysis: NarrativeAnalysis = structured_analyst.invoke(
            [HumanMessage(content=phase_a_prompt)]
        )
        log.info(
            "assemble_scene: scene %s — %d buckets, %d assignments, %d pruned",
            sid, len(analysis.buckets), len(analysis.assignments),
            len(analysis.pruned_segment_ids),
        )

        # Guard: if no assignments, skip pathfinding
        if not analysis.assignments:
            log.warning("assemble_scene: scene %s has no bucket assignments — skipping", sid)
            return {
                "narrative_analyses": {sid: analysis.model_dump()},
                "chains_per_scene": {sid: []},
                "chain_selections": {
                    sid: ChainSelection(
                        scene_id=scene["id"],
                        selected_chain_index=0,
                        reasoning="No assignments returned by narrative analyst; skipping.",
                    ).model_dump()
                },
                }

        # ── Phase B: DAG + k-shortest paths ──────────────────────────────────
        log.info("assemble_scene: scene %s — Phase B (pathfinding)", sid)
        dag = build_dag(
            scene_id=scene["id"],
            assignments=[a.model_dump() for a in analysis.assignments],
            segments_by_id=segments_by_id,
            cfg=cfg,
        )
        chains: list[Chain] = find_chains(
            dag=dag,
            segments_by_id=segments_by_id,
            assignments=[a.model_dump() for a in analysis.assignments],
            scene_id=scene["id"],
            target_min=analysis.target_duration_min,
            target_max=analysis.target_duration_max,
            target_ideal=analysis.target_duration_ideal,
            top_k=top_k_chains,
            cfg=cfg,
        )
        log.info("assemble_scene: scene %s — %d chains found", sid, len(chains))

        if not chains:
            return {
                "narrative_analyses": {sid: analysis.model_dump()},
                "chains_per_scene": {sid: []},
                "chain_selections": {
                    sid: ChainSelection(
                        scene_id=scene["id"],
                        selected_chain_index=0,
                        reasoning="No chains found by pathfinder.",
                    ).model_dump()
                },
                }

        # ── Phase C: Editorial selection ──────────────────────────────────────
        log.info("assemble_scene: scene %s — Phase C (editorial selection)", sid)
        chains_text = _format_chains([c.model_dump() for c in chains], segments_by_id)
        phase_c_prompt = EDITORIAL_SELECTOR_PROMPT.format(
            scene_id=scene["id"],
            scene_description=scene.get("scene_description", ""),
            top_k=len(chains),
            target_duration_ideal=analysis.target_duration_ideal,
            target_duration_min=analysis.target_duration_min,
            target_duration_max=analysis.target_duration_max,
            chains_formatted=chains_text,
        )
        selection: ChainSelection = structured_selector.invoke(
            [HumanMessage(content=phase_c_prompt)]
        )

        # Apply gate2 overrides if present
        override = gate2_overrides.get(sid)
        if override:
            selection.selected_chain_index = override.get("chain_index", selection.selected_chain_index)
            selection.override_notes = override.get("notes", "")
            log.info("assemble_scene: scene %s — gate2 override applied", sid)

        # Clamp to valid range
        selection.selected_chain_index = max(
            0, min(selection.selected_chain_index, len(chains) - 1)
        )
        selected_chain = chains[selection.selected_chain_index]
        selected_seg_ids = [lnk.segment_id for lnk in selected_chain.links]
        log.info(
            "assemble_scene: scene %s — selected chain %d, segments: %s",
            sid, selection.selected_chain_index, selected_seg_ids,
        )

        return {
            "narrative_analyses": {sid: analysis.model_dump()},
            "chains_per_scene": {sid: [c.model_dump() for c in chains]},
            "chain_selections": {sid: selection.model_dump()},
        }

    return assemble_scene_node


# ── (legacy name kept for any direct callers — delegates to new split nodes) ──

def make_assemble_scenes_node(
    analyst_llm: BaseChatModel,
    selector_llm: BaseChatModel,
    cfg,
):
    """Deprecated: superseded by make_dispatch_scenes_node + make_assemble_scene_node.

    Kept so that external code importing this name does not break immediately.
    The graph no longer uses this node.
    """
    structured_analyst = analyst_llm.with_structured_output(NarrativeAnalysis)
    structured_selector = selector_llm.with_structured_output(ChainSelection)

    from editor.tools.pathfinding import build_dag, find_chains

    def assemble_scenes_node(state: EditorState) -> dict:
        segments_by_id: dict[str, dict] = {s["segment_id"]: s for s in state["segments"]}

        narrative_analyses = dict(state.get("narrative_analyses") or {})
        chains_per_scene = dict(state.get("chains_per_scene") or {})
        chain_selections = dict(state.get("chain_selections") or {})

        # Determine which scenes to process.
        # is_reassembly is True for both the human Gate 2 path (flagged_scene_ids set)
        # and the automated review loop path (a prior review exists).  This ensures
        # gate2_round increments on every re-entry so max_gate2_rounds terminates the loop.
        flagged = state.get("flagged_scene_ids") or []
        is_reassembly = bool(flagged) or (state.get("review") is not None)
        scenes_to_process = [
            s for s in state["scenes"]
            if str(s["id"]) in state["deduped_candidates"]
            and (not flagged or s["id"] in flagged)
        ]

        for scene in scenes_to_process:
            sid = str(scene["id"])
            candidates = state["deduped_candidates"].get(sid, [])
            log.info(
                "assemble_scenes: scene %s — Phase A (narrative analysis, %d candidates)",
                sid, len(candidates),
            )

            # ── Phase A: Narrative analysis ───────────────────────────────────
            candidate_list_text = _format_candidates(candidates, segments_by_id)
            phase_a_prompt = NARRATIVE_ANALYST_PROMPT.format(
                scene_id=scene["id"],
                narration_text=scene.get("narration_segment", ""),
                scene_description=scene.get("scene_description", ""),
                keywords=", ".join(scene.get("keywords", [])),
                candidate_list=candidate_list_text,
            )
            analysis: NarrativeAnalysis = structured_analyst.invoke(
                [HumanMessage(content=phase_a_prompt)]
            )
            narrative_analyses[sid] = analysis.model_dump()
            log.info(
                "assemble_scenes: scene %s — %d buckets, %d assignments, %d pruned",
                sid, len(analysis.buckets), len(analysis.assignments),
                len(analysis.pruned_segment_ids),
            )

            # Guard: if no assignments, skip pathfinding
            if not analysis.assignments:
                log.warning("assemble_scenes: scene %s has no bucket assignments — skipping", sid)
                chains_per_scene[sid] = []
                chain_selections[sid] = ChainSelection(
                    scene_id=scene["id"],
                    selected_chain_index=0,
                    reasoning="No assignments returned by narrative analyst; skipping.",
                ).model_dump()
                continue

            # ── Phase B: DAG + k-shortest paths ──────────────────────────────
            log.info("assemble_scenes: scene %s — Phase B (pathfinding)", sid)
            dag = build_dag(
                scene_id=scene["id"],
                assignments=[a.model_dump() for a in analysis.assignments],
                segments_by_id=segments_by_id,
                cfg=cfg,
            )
            chains: list[Chain] = find_chains(
                dag=dag,
                segments_by_id=segments_by_id,
                assignments=[a.model_dump() for a in analysis.assignments],
                scene_id=scene["id"],
                target_min=analysis.target_duration_min,
                target_max=analysis.target_duration_max,
                target_ideal=analysis.target_duration_ideal,
                top_k=state["top_k_chains"],
                cfg=cfg,
            )
            chains_per_scene[sid] = [c.model_dump() for c in chains]
            log.info("assemble_scenes: scene %s — %d chains found", sid, len(chains))

            if not chains:
                chain_selections[sid] = ChainSelection(
                    scene_id=scene["id"],
                    selected_chain_index=0,
                    reasoning="No chains found by pathfinder.",
                ).model_dump()
                continue

            # ── Phase C: Editorial selection ──────────────────────────────────
            log.info("assemble_scenes: scene %s — Phase C (editorial selection)", sid)
            chains_text = _format_chains([c.model_dump() for c in chains], segments_by_id)
            phase_c_prompt = EDITORIAL_SELECTOR_PROMPT.format(
                scene_id=scene["id"],
                scene_description=scene.get("scene_description", ""),
                top_k=len(chains),
                target_duration_ideal=analysis.target_duration_ideal,
                target_duration_min=analysis.target_duration_min,
                target_duration_max=analysis.target_duration_max,
                chains_formatted=chains_text,
            )
            selection: ChainSelection = structured_selector.invoke(
                [HumanMessage(content=phase_c_prompt)]
            )

            # Apply gate2 overrides if present
            override = (state.get("gate2_overrides") or {}).get(sid)
            if override:
                selection.selected_chain_index = override.get("chain_index", selection.selected_chain_index)
                selection.override_notes = override.get("notes", "")
                log.info("assemble_scenes: scene %s — gate2 override applied", sid)

            # Clamp to valid range
            selection.selected_chain_index = max(
                0, min(selection.selected_chain_index, len(chains) - 1)
            )
            chain_selections[sid] = selection.model_dump()
            selected_chain = chains[selection.selected_chain_index]
            selected_seg_ids = [lnk.segment_id for lnk in selected_chain.links]
            log.info(
                "assemble_scenes: scene %s — selected chain %d, segments: %s",
                sid, selection.selected_chain_index, selected_seg_ids,
            )

        new_gate2_round = (
            state["gate2_round"] + 1 if is_reassembly else state["gate2_round"]
        )
        return {
            "narrative_analyses": narrative_analyses,
            "chains_per_scene": chains_per_scene,
            "chain_selections": chain_selections,
            "flagged_scene_ids": [],   # clear after processing
            "gate2_round": new_gate2_round,
        }

    return assemble_scenes_node


# ── Node: fill gaps ───────────────────────────────────────────────────────────

def make_fill_gaps_node(cfg):
    """For scenes with too few candidates after dedup, pull from unassigned segments."""
    from editor.tools.embedding import get_index, retrieve_candidates

    def fill_gaps_node(state: EditorState) -> dict:
        deduped = {sid: list(pool) for sid, pool in state["deduped_candidates"].items()}

        # Collect segments already assigned to any scene
        assigned_ids: set[str] = {
            c["segment_id"] for pool in deduped.values() for c in pool
        }

        gap_scenes = [
            sid for sid, pool in deduped.items()
            if len(pool) < state["min_candidates_per_scene"]
        ]
        if not gap_scenes:
            return {}

        matrix, ids = get_index()
        unassigned_id_set = {
            s["segment_id"] for s in state["segments"]
            if s["segment_id"] not in assigned_ids
        }

        gap_warnings: list[str] = []
        for sid in gap_scenes:
            pool = deduped[sid]
            needed = state["min_candidates_per_scene"] - len(pool)
            scene = next((s for s in state["scenes"] if str(s["id"]) == sid), None)
            if scene is None:
                continue

            # Retrieve from full index, filter to unassigned only
            extra_candidates = [
                c for c in retrieve_candidates(scene, state["segments"], matrix, ids, cfg)
                if c.segment_id in unassigned_id_set
            ]
            added = extra_candidates[:needed]
            for c in added:
                pool.append(c.model_dump())
                assigned_ids.add(c.segment_id)
                unassigned_id_set.discard(c.segment_id)

            log.info(
                "fill_gaps: scene %s — added %d segment(s) from unassigned pool (pool now %d)",
                sid, len(added), len(pool),
            )
            if len(pool) < state["min_candidates_per_scene"]:
                msg = (
                    f"Scene {sid} still has only {len(pool)} candidate(s) after gap fill "
                    f"(minimum {state['min_candidates_per_scene']})"
                )
                log.warning("fill_gaps: %s", msg)
                gap_warnings.append(msg)

        return {"deduped_candidates": deduped, "gap_warnings": gap_warnings}

    return fill_gaps_node


# ── Node: stitch scenes ────────────────────────────────────────────────────────

def make_stitch_scenes_node(stitcher_llm: BaseChatModel, cfg):
    structured_stitcher = stitcher_llm.with_structured_output(StitchDecision)

    from editor.tools.stitching import compute_boundary_cost, find_swap_candidates

    def stitch_scenes_node(state: EditorState) -> dict:
        segments_by_id: dict[str, dict] = {s["segment_id"]: s for s in state["segments"]}
        scenes = state["scenes"]
        boundaries: list[dict] = []
        stitch_decisions: list[dict] = []

        for i in range(len(scenes) - 1):
            scene_a = scenes[i]
            scene_b = scenes[i + 1]
            chain_a = _get_selected_chain(state, scene_a["id"])
            chain_b = _get_selected_chain(state, scene_b["id"])

            if not chain_a or not chain_b:
                log.warning(
                    "stitch: boundary %d–%d skipped — missing chain", scene_a["id"], scene_b["id"]
                )
                continue

            links_a = chain_a.get("links", [])
            links_b = chain_b.get("links", [])
            if not links_a or not links_b:
                continue

            seg_id_a = links_a[-1]["segment_id"]
            seg_id_b = links_b[0]["segment_id"]
            seg_a = segments_by_id.get(seg_id_a, {})
            seg_b = segments_by_id.get(seg_id_b, {})

            cost = compute_boundary_cost(seg_a, seg_b, cfg)
            flagged = cost > cfg.stitching_cost_threshold

            boundary = BoundaryInfo(
                scene_id_a=scene_a["id"],
                scene_id_b=scene_b["id"],
                segment_id_a=seg_id_a,
                segment_id_b=seg_id_b,
                kinematic_cost=cost,
                flagged=flagged,
            )
            boundaries.append(boundary.model_dump())

            if not flagged:
                decision = StitchDecision(
                    boundary_idx=i,
                    action="accept",
                    reasoning=f"Kinematic cost {cost:.3f} is below threshold {cfg.stitching_cost_threshold:.3f}.",
                )
                stitch_decisions.append(decision.model_dump())
                log.info("stitch: boundary %d clean (cost=%.3f)", i, cost)
                continue

            # Flagged boundary — LLM resolves
            log.info("stitch: boundary %d flagged (cost=%.3f)", i, cost)
            candidates_b = (state.get("deduped_candidates") or {}).get(str(scene_b["id"]), [])
            swap_ids = find_swap_candidates(
                current_entry_seg_id=seg_id_b,
                candidates=candidates_b,
                segments_by_id=segments_by_id,
                predecessor_seg=seg_a,
                cfg=cfg,
            )
            swap_text = _format_swap_candidates(swap_ids, segments_by_id, seg_a)

            vlm_a = seg_a.get("vlm", [])
            desc_a = vlm_a[0].get("description", "(no description)") if vlm_a else "(no description)"
            vlm_b = seg_b.get("vlm", [])
            desc_b = vlm_b[0].get("description", "(no description)") if vlm_b else "(no description)"

            prompt = STITCHING_PROMPT.format(
                scene_id_a=scene_a["id"],
                scene_id_b=scene_b["id"],
                scene_a_description=scene_a.get("scene_description", ""),
                scene_b_description=scene_b.get("scene_description", ""),
                exit_segment_id=seg_id_a,
                exit_segment_description=desc_a,
                entry_segment_id=seg_id_b,
                entry_segment_description=desc_b,
                kinematic_cost=cost,
                threshold=cfg.stitching_cost_threshold,
                swap_candidates_formatted=swap_text,
            )
            decision: StitchDecision = structured_stitcher.invoke([HumanMessage(content=prompt)])
            decision.boundary_idx = i
            stitch_decisions.append(decision.model_dump())
            log.info(
                "stitch: boundary %d resolved → action=%s", i, decision.action
            )

        return {"boundaries": boundaries, "stitch_decisions": stitch_decisions}

    return stitch_scenes_node


# ── Node: automated review ─────────────────────────────────────────────────────

def make_review_timeline_node(reviewer_llm: BaseChatModel):
    structured_reviewer = reviewer_llm.with_structured_output(TimelineReview)

    def review_timeline_node(state: EditorState) -> dict:
        log.info("review_timeline: running automated review")
        segments_by_id: dict[str, dict] = {s["segment_id"]: s for s in state["segments"]}

        # Build timeline summary text
        timeline_lines: list[str] = []
        for scene in state["scenes"]:
            sid = str(scene["id"])
            chain = _get_selected_chain(state, scene["id"])
            if not chain:
                timeline_lines.append(f"Scene {scene['id']}: (no chain selected)")
                continue
            links = chain.get("links", [])
            seg_descs = []
            for link in links:
                seg = segments_by_id.get(link["segment_id"], {})
                vlm_list = seg.get("vlm", [])
                desc = (vlm_list[0].get("description", "")[:60] if vlm_list else "")
                seg_descs.append(f"{link['segment_id']} ({desc})")
            timeline_lines.append(
                f"Scene {scene['id']} [{scene.get('scene_description', '')[:80]}] "
                f"— {chain['total_duration']:.1f}s — {' → '.join(seg_descs)}"
            )

        storyboard_text = "\n".join(
            f"Scene {s['id']}: {s.get('scene_description', '')}" for s in state["scenes"]
        )
        boundary_text = "\n".join(
            f"Boundary {b.get('scene_id_a')}→{b.get('scene_id_b')}: "
            f"cost={b.get('kinematic_cost', 0):.3f} flagged={b.get('flagged')}"
            for b in state["boundaries"]
        )

        prompt = REVIEWER_PROMPT.format(
            storyboard_scenes=storyboard_text,
            timeline_summary="\n".join(timeline_lines),
            boundary_summary=boundary_text,
        )
        review: TimelineReview | None = structured_reviewer.invoke([HumanMessage(content=prompt)])
        if review is None:
            log.warning("review_timeline: LLM returned None — using fallback approve review")
            review = TimelineReview(
                overall_score=0.5,
                scene_notes=[],
                has_structural_issues=False,
                auto_fix_applied=[],
                decision="approve",
            )
        log.info(
            "review_timeline: score=%.2f structural_issues=%s decision=%s",
            review.overall_score, review.has_structural_issues, review.decision,
        )
        return {"review": review.model_dump()}

    return review_timeline_node


# ── Node: persist timeline ─────────────────────────────────────────────────────

def make_persist_timeline_node(storage, project_name: str):
    from core.schemas.editor import (
        BoundaryInfo,
        SceneTimeline,
        StitchDecision,
        TimelineOutput,
        TimelineReview,
        TimelineSegmentEntry,
    )

    def persist_timeline_node(state: EditorState) -> dict:
        segments_by_id: dict[str, dict] = {s["segment_id"]: s for s in state["segments"]}
        position = 1
        scene_timelines: list[SceneTimeline] = []

        for scene in state["scenes"]:
            sid = str(scene["id"])
            chain = _get_selected_chain(state, scene["id"])
            if not chain:
                log.warning("persist: scene %s has no selected chain — including as empty", sid)
                scene_timelines.append(SceneTimeline(
                    scene_id=scene["id"],
                    scene_description=scene.get("scene_description", ""),
                    chain_cost=0.0,
                    total_duration=0.0,
                    entries=[],
                ))
                continue

            entries: list[TimelineSegmentEntry] = []
            for link in chain.get("links", []):
                seg = segments_by_id.get(link["segment_id"], {})
                vlm_list = seg.get("vlm", [])
                quality = "good"
                if vlm_list and vlm_list[0].get("quality_score"):
                    quality = vlm_list[0]["quality_score"].get("rating", "good") or "good"

                # Determine stitch action from stitch_decisions
                stitch_action = "cut"
                for sd in state.get("stitch_decisions", []):
                    # Check if this is the entry segment of a boundary decision
                    boundaries = state.get("boundaries", [])
                    if sd.get("boundary_idx") is not None:
                        b_idx = sd["boundary_idx"]
                        if b_idx < len(boundaries):
                            b = boundaries[b_idx]
                            if b.get("segment_id_b") == link["segment_id"]:
                                action = sd.get("action", "accept")
                                if action == "transition":
                                    stitch_action = sd.get("transition_type", "dissolve") or "dissolve"

                entries.append(TimelineSegmentEntry(
                    position=position,
                    scene_id=scene["id"],
                    segment_id=link["segment_id"],
                    video_file=link.get("video_file", seg.get("video_file", "")),
                    source_video=seg.get("source_video", ""),
                    start=link["start"],
                    end=link["end"],
                    duration=link["end"] - link["start"],
                    bucket_idx=link["bucket_idx"],
                    quality_rating=quality,
                    edge_cost=link.get("edge_cost", 0.0),
                    stitch_action=stitch_action,
                ))
                position += 1

            scene_timelines.append(SceneTimeline(
                scene_id=scene["id"],
                scene_description=scene.get("scene_description", ""),
                chain_cost=chain.get("total_cost", 0.0),
                total_duration=chain.get("total_duration", 0.0),
                entries=entries,
            ))

        total_duration = sum(st.total_duration for st in scene_timelines)
        total_segments = sum(len(st.entries) for st in scene_timelines)

        review_obj: TimelineReview | None = None
        if state.get("review"):
            try:
                review_obj = TimelineReview.model_validate(state["review"])
            except Exception:
                pass

        output = TimelineOutput(
            project_name=state["project_name"],
            storyboard_version=state["storyboard_version"],
            scenes=scene_timelines,
            boundaries=[BoundaryInfo.model_validate(b) for b in state.get("boundaries", [])],
            stitch_decisions=[StitchDecision.model_validate(sd) for sd in state.get("stitch_decisions", [])],
            review=review_obj,
            gate2_round=state["gate2_round"],
            approved=state.get("approved", False),
            total_duration=total_duration,
            total_segments=total_segments,
        )

        version = storage.save_versioned(project_name, "timeline", output)
        log.info(
            "persist: saved timeline v%d for project '%s' — %d scenes, %.1fs, %d segments",
            version, project_name, len(scene_timelines), total_duration, total_segments,
        )
        return {}

    return persist_timeline_node
