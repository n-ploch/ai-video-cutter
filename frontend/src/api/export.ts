import api from './client'

export interface ExportResponse {
  version: string
  otio_url: string
  total_segments: number
  total_duration: number
}

export async function triggerExport(
  project: string,
  rate = 30.0,
): Promise<ExportResponse> {
  return api
    .post(`api/v1/projects/${project}/export`, {
      json: { version: 'latest', rate },
    })
    .json()
}
