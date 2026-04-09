export interface VideoProcessingStatus {
  video_hash: string
  filename: string
  steps: Record<string, string | null>
  config_hash: string | null
  storage_key: string | null
  celery_task_id: string | null
  celery_state: string | null
  current_step: string | null
}

export interface VideoUploadResponse {
  video_hash: string
  filename: string
  task_id: string
  status: string
}

export interface VideoVlm {
  description: string
  key_subjects: string[][]
  tone: string[]
  genre_or_type: string
  tags: string[]
}

export interface VideoDescription {
  video_id: string
  video_file: string
  vlm: VideoVlm
}
