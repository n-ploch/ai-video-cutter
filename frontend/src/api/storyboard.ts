import type { TaskResponse } from '../types/status'
import type { StoryboardOutput } from '../types/storyboard'
import api from './client'

export async function triggerStoryboard(
  project: string,
  brief: string,
): Promise<TaskResponse> {
  return api
    .post(`api/v1/projects/${project}/storyboard`, {
      json: { brief, human_in_the_loop: false },
    })
    .json()
}

export async function getStoryboard(project: string): Promise<StoryboardOutput> {
  return api.get(`api/v1/projects/${project}/storyboard`).json()
}
