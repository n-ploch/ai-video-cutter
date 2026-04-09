import type { ProjectResponse, ProjectDetailResponse } from '../types/project'
import api from './client'

export async function listProjects(): Promise<ProjectResponse[]> {
  return api.get('api/v1/projects').json()
}

export async function createProject(name: string): Promise<ProjectResponse> {
  return api.post('api/v1/projects', { json: { name } }).json()
}

export async function getProject(name: string): Promise<ProjectDetailResponse> {
  return api.get(`api/v1/projects/${name}`).json()
}

export async function deleteProject(name: string): Promise<void> {
  await api.delete(`api/v1/projects/${name}`)
}
