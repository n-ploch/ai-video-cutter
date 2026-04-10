import type { TaskResponse } from '../types/status'
import type { TimelineOutput } from '../types/timeline'
import type { TimelineVersionInfo } from '../types/versions'
import api from './client'

export async function triggerEditor(
  project: string,
  storyboardVersion?: number | null,
): Promise<TaskResponse> {
  return api
    .post(`api/v1/projects/${project}/editor`, {
      json: {
        human_in_the_loop: false,
        ...(storyboardVersion != null ? { storyboard_version: storyboardVersion } : {}),
      },
    })
    .json()
}

export async function getTimeline(
  project: string,
  version?: number,
): Promise<TimelineOutput> {
  const url =
    version != null
      ? `api/v1/projects/${project}/editor?version=${version}`
      : `api/v1/projects/${project}/editor`
  return api.get(url).json()
}

export async function getEditorVersions(
  project: string,
): Promise<TimelineVersionInfo[]> {
  return api.get(`api/v1/projects/${project}/editor/versions`).json()
}
