export interface StoryboardVersionInfo {
  version: number
  created_at: string
  brief_snippet: string | null
}

export interface TimelineVersionInfo {
  version: number
  created_at: string
  storyboard_version: number | null
  brief_snippet: string | null
}
