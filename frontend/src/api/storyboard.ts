import type { TaskResponse } from '../types/status'
import type { StoryboardOutput } from '../types/storyboard'
import type { StoryboardVersionInfo } from '../types/versions'
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

export async function getStoryboard(
  project: string,
  version?: number,
): Promise<StoryboardOutput> {
  const url =
    version != null
      ? `api/v1/projects/${project}/storyboard?version=${version}`
      : `api/v1/projects/${project}/storyboard`
  return api.get(url).json()
}

export async function getStoryboardVersions(
  project: string,
): Promise<StoryboardVersionInfo[]> {
  return api.get(`api/v1/projects/${project}/storyboard/versions`).json()
}
