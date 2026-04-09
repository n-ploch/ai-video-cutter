import type { VideoProcessingStatus, VideoUploadResponse } from '../types/video'
import api from './client'

export async function listVideos(project: string): Promise<VideoProcessingStatus[]> {
  return api.get(`api/v1/projects/${project}/videos`).json()
}

export async function uploadVideo(
  project: string,
  file: File,
  includeVlm = true,
): Promise<VideoUploadResponse> {
  const form = new FormData()
  form.append('file', file)
  return api
    .post(`api/v1/projects/${project}/videos`, {
      body: form,
      searchParams: { include_vlm: String(includeVlm) },
      headers: {},
      timeout: 300_000,
    })
    .json()
}

export async function getVideoStatus(
  project: string,
  videoHash: string,
): Promise<VideoProcessingStatus> {
  return api.get(`api/v1/projects/${project}/videos/${videoHash}/status`).json()
}
