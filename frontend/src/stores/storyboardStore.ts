import { create } from 'zustand'
import type { StoryboardOutput } from '../types/storyboard'
import * as storyboardApi from '../api/storyboard'
import { getTaskStatus } from '../api/status'

interface StoryboardStore {
  storyboard: StoryboardOutput | null
  taskId: string | null
  isRunning: boolean
  error: string | null
  submittedBrief: string | null

  triggerStoryboard: (project: string, brief: string) => Promise<void>
  fetchStoryboard: (project: string) => Promise<void>
  pollStatus: () => Promise<boolean> // returns true when done
  reset: () => void
}

export const useStoryboardStore = create<StoryboardStore>((set, get) => ({
  storyboard: null,
  taskId: null,
  isRunning: false,
  error: null,
  submittedBrief: null,

  triggerStoryboard: async (project, brief) => {
    set({ isRunning: true, error: null, submittedBrief: brief, storyboard: null })
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

  pollStatus: async () => {
    const { taskId } = get()
    if (!taskId) return true
    try {
      const res = await getTaskStatus(taskId)
      if (res.status === 'SUCCESS') {
        set({ isRunning: false })
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
    }),
}))
