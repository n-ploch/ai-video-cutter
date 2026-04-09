import { create } from 'zustand'
import type { ProjectResponse } from '../types/project'
import * as projectsApi from '../api/projects'

interface ProjectStore {
  projects: ProjectResponse[]
  currentProject: string | null
  loading: boolean
  error: string | null

  fetchProjects: () => Promise<void>
  createProject: (name: string) => Promise<ProjectResponse>
  selectProject: (name: string | null) => void
}

export const useProjectStore = create<ProjectStore>((set, get) => ({
  projects: [],
  currentProject: null,
  loading: false,
  error: null,

  fetchProjects: async () => {
    set({ loading: true, error: null })
    try {
      const projects = await projectsApi.listProjects()
      set({ projects, loading: false })
    } catch (e) {
      set({ error: String(e), loading: false })
    }
  },

  createProject: async (name: string) => {
    const project = await projectsApi.createProject(name)
    await get().fetchProjects()
    set({ currentProject: project.name })
    return project
  },

  selectProject: (name: string | null) => {
    set({ currentProject: name })
  },
}))
