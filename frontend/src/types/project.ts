export interface ProjectResponse {
  id: string
  name: string
  status: string
  created_at: string
  video_count: number
  has_storyboard: boolean
  has_timeline: boolean
}

export interface AgentTaskStatus {
  task_id: string | null
  celery_state: string | null
  has_output: boolean
  awaiting_human: boolean
  thread_id: string | null
  paused_at: string[]
}

export interface ProjectDetailResponse extends ProjectResponse {
  videos: import('./video').VideoProcessingStatus[]
  storyboard: AgentTaskStatus
  editor: AgentTaskStatus
  config: Record<string, unknown>
}
