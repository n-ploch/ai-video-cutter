import { create } from 'zustand'
import type { StoryboardOutput } from '../types/storyboard'
import type { StoryboardVersionInfo } from '../types/versions'
import * as storyboardApi from '../api/storyboard'
import { getTaskStatus } from '../api/status'

interface StoryboardStore {
  // Active/latest storyboard (polled during generation, loaded on mount)
  storyboard: StoryboardOutput | null
  taskId: string | null
  isRunning: boolean
  error: string | null
  submittedBrief: string | null

  // Version history
  versions: StoryboardVersionInfo[]
  selectedVersion: number | null       // null = show active/latest
  viewingStoryboard: StoryboardOutput | null  // loaded when selectedVersion is set

  triggerStoryboard: (project: string, brief: string) => Promise<void>
  fetchStoryboard: (project: string) => Promise<void>
  fetchVersions: (project: string) => Promise<void>
  selectVersion: (project: string, version: number | null) => Promise<void>
  startNew: () => void
  pollStatus: (project: string) => Promise<boolean> // returns true when done
  reset: () => void
}

export const useStoryboardStore = create<StoryboardStore>((set, get) => ({
  storyboard: null,
  taskId: null,
  isRunning: false,
  error: null,
  submittedBrief: null,
  versions: [],
  selectedVersion: null,
  viewingStoryboard: null,

  triggerStoryboard: async (project, brief) => {
    set({
      isRunning: true,
      error: null,
      submittedBrief: brief,
      storyboard: null,
      selectedVersion: null,
      viewingStoryboard: null,
    })
    try {
      const res = await storyboardApi.triggerStoryboard(project, brief)
      set({ taskId: res.task_id })
    } catch (e) {
      set({ isRunning: false, error: String(e) })
    }
  },

  fetchStoryboard: async (project) => {
    try {
      const data = await storyboardApi.getStoryboard(project)
      set({ storyboard: data })
    } catch {
      // Not ready yet
    }
  },

  fetchVersions: async (project) => {
    try {
      const versions = await storyboardApi.getStoryboardVersions(project)
      set({ versions })
    } catch {
      // Ignore — no versions yet
    }
  },

  selectVersion: async (project, version) => {
    if (version === null) {
      set({ selectedVersion: null, viewingStoryboard: null })
      return
    }
    try {
      const data = await storyboardApi.getStoryboard(project, version)
      set({ selectedVersion: version, viewingStoryboard: data })
    } catch {
      // Ignore load error
    }
  },

  startNew: () => {
    set({
      selectedVersion: null,
      viewingStoryboard: null,
      storyboard: null,
      submittedBrief: null,
      error: null,
    })
  },

  pollStatus: async (project) => {
    const { taskId } = get()
    if (!taskId) return true
    try {
      const res = await getTaskStatus(taskId)
      if (res.status === 'SUCCESS') {
        set({ isRunning: false })
        // Refresh versions list so the new version appears in sidebar
        get().fetchVersions(project)
        return true
      }
      if (res.status === 'FAILURE') {
        set({ isRunning: false, error: res.error ?? 'Storyboard generation failed' })
        return true
      }
      return false
    } catch {
      return false
    }
  },

  reset: () =>
    set({
      storyboard: null,
      taskId: null,
      isRunning: false,
      error: null,
      submittedBrief: null,
      versions: [],
      selectedVersion: null,
      viewingStoryboard: null,
    }),
}))
