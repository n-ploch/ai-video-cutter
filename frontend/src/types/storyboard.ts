export interface NarrationBeat {
  id: number
  text: string
}

export interface StoryboardScene {
  id: number
  narration_segment: string
  scene_description: string
  reasoning: string
  keywords: string[]
}

export interface StoryJudgeResult {
  narrative_quality: number
  brief_adherence: number
  context_adherence: number
  total_score: number
  feedback: string
  decision: string
}

export interface JudgeResult {
  score: number
  feedback: string
  decision: string
}

export interface StoryboardOutput {
  user_brief: string
  story: string
  narration_beats: NarrationBeat[]
  scenes: StoryboardScene[]
  story_judge_result: StoryJudgeResult | null
  story_revision_count: number
  judge_result: JudgeResult
  revision_count: number
}
