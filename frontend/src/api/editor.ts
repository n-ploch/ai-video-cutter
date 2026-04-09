import type { TaskResponse } from '../types/status'
import type { TimelineOutput } from '../types/timeline'
import api from './client'

export async function triggerEditor(project: string): Promise<TaskResponse> {
  return api
    .post(`api/v1/projects/${project}/editor`, {
      json: { human_in_the_loop: false },
    })
    .json()
}

export async function getTimeline(project: string): Promise<TimelineOutput> {
  return api.get(`api/v1/projects/${project}/editor`).json()
}
