export interface TimelineSegmentEntry {
  position: number
  scene_id: number
  segment_id: string
  video_file: string
  source_video: string
  start: number
  end: number
  duration: number
  bucket_idx: number
  quality_rating: string
  edge_cost: number
  stitch_action: string
}

export interface SceneTimeline {
  scene_id: number
  scene_description: string
  chain_cost: number
  total_duration: number
  entries: TimelineSegmentEntry[]
}

export interface BoundaryInfo {
  scene_id_a: number
  scene_id_b: number
  segment_id_a: string
  segment_id_b: string
  kinematic_cost: number
  flagged: boolean
}

export interface StitchDecision {
  boundary_idx: number
  action: string
  transition_type: string
  swap_segment_id: string
  reasoning: string
}

export interface SceneReviewNote {
  scene_id: number | null
  issue: string
  severity: string
  suggestion: string
}

export interface TimelineReview {
  overall_score: number
  scene_notes: SceneReviewNote[]
  has_structural_issues: boolean
  auto_fix_applied: string[]
  decision: string
}

export interface TimelineOutput {
  project_name: string
  storyboard_version?: number
  scenes: SceneTimeline[]
  boundaries: BoundaryInfo[]
  stitch_decisions: StitchDecision[]
  review: TimelineReview | null
  gate2_round: number
  approved: boolean
  total_duration: number
  total_segments: number
}
