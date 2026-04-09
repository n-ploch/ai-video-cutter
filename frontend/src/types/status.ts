export interface TaskResponse {
  task_id: string
  status: string
  result: Record<string, unknown> | null
  error: string | null
}
