export interface CameraMovement {
  movement_id: number
  start_time: number
  end_time: number
  pan_entry_vel: number
  tilt_entry_vel: number
  zoom_entry_vel: number
  pan_exit_vel: number
  tilt_exit_vel: number
  zoom_exit_vel: number
  pan_monotonicity: number
  tilt_monotonicity: number
  zoom_monotonicity: number
  pan_mean_abs_deriv: number
  tilt_mean_abs_deriv: number
  zoom_mean_abs_deriv: number
  pan_std_deriv: number
  tilt_std_deriv: number
  zoom_std_deriv: number
}

export interface SegmentBase {
  segment_id: string
  video_file: string
  source_video: string
  start: number
  end: number
  camera_movements: CameraMovement[]
}

export interface TechnicalSpecsReasoning {
  framing: string
  movement: string
  angle: string
}

export interface TechnicalSpecs {
  framing: string
  movement: string
  angle: string
  reasoning: TechnicalSpecsReasoning
}

export interface ColorProfile {
  dominant_colors: string[]
  lighting_type: string
  temperature: string
}

export interface Highlight {
  description: string
  keywords: string[]
  start: string
  end: string
}

export interface QualityScore {
  rating: string
  reasoning: string
}

export interface SegmentDescription {
  segment_id: string
  description: string
  technical_specs: TechnicalSpecs | null
  color_profile: ColorProfile | null
  highlights: Highlight[]
  quality_score: QualityScore | null
  segment_tags: string[]
}
