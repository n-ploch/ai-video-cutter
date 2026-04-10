import { create } from 'zustand'
import type { StoryboardOutput } from '../types/storyboard'
import type { StoryboardVersionInfo } from '../types/versions'
import * as storyboardApi from '../api/storyboard'
import { getTaskStatus, getProjectStatus } from '../api/status'

interface StoryboardStore {
  // Active/latest storyboard (polled during generation, loaded on mount)
  storyboard: StoryboardOutput | null
  taskId: string | null
  isRunning: boolean
  error: string | null
  submittedBrief: string | null

  // Version history
  versions: StoryboardVersionInfo[]
  selectedVersion: number | null        // null = active/create-new view
  viewingStoryboard: StoryboardOutput | null  // loaded when selectedVersion is set

  triggerStoryboard: (project: string, brief: string) => Promise<void>
  fetchStoryboard: (project: string) => Promise<void>
  fetchVersions: (project: string) => Promise<void>
  /**
   * Re-hydrate isRunning/taskId from the backend project status.
   * Called on mount to recover running task state after a page refresh.
   * Safe to call when already running — will not overwrite state.
   */
  hydrateTaskState: (project: string) => Promise<void>
  selectVersion: (project: string, version: number | null) => Promise<void>
  /**
   * Enter the "create new" view: clears active storyboard/brief so the
   * chat input appears fresh. Does NOT clear versions or selectedVersion
   * directly — the caller should also call selectVersion(project, null).
   */
  startNew: () => void
  pollStatus: (project: string) => Promise<boolean>
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
      // No versions yet
    }
  },

  hydrateTaskState: async (project) => {
    // Don't overwrite an already-known running state (same session, tab navigation).
    if (get().isRunning) return
    try {
      const status = await getProjectStatus(project)
      const sb = status.storyboard
      // Only STARTED and RETRY mean the task is genuinely in flight.
      // PENDING is Celery's default for unknown/expired task IDs and must be ignored.
      if (
        sb.task_id &&
        (sb.celery_state === 'STARTED' || sb.celery_state === 'RETRY')
      ) {
        set({ isRunning: true, taskId: sb.task_id })
      }
    } catch {
      // Ignore — backend may not be reachable yet
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
    // Clear active content so chat input appears blank.
    // selectedVersion is intentionally NOT set here — the caller pairs this
    // with selectVersion(project, null) so the sidebar also deselects.
    set({
      storyboard: null,
      submittedBrief: null,
      error: null,
      viewingStoryboard: null,
      selectedVersion: null,
    })
  },

  pollStatus: async (project) => {
    const { taskId } = get()
    // No task ID yet — triggerStoryboard is still awaiting the API response.
    // Return false so polling keeps running rather than fetching stale data.
    if (!taskId) return false
    try {
      const res = await getTaskStatus(taskId)
      if (res.status === 'SUCCESS') {
        set({ isRunning: false })
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
