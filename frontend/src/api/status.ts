import type { TaskResponse } from '../types/status'
import type { ProjectDetailResponse } from '../types/project'
import api from './client'

export async function getTaskStatus(taskId: string): Promise<TaskResponse> {
  return api.get(`api/v1/status/${taskId}`).json()
}

export async function getProjectStatus(project: string): Promise<ProjectDetailResponse> {
  return api.get(`api/v1/projects/${project}/status`).json()
}
