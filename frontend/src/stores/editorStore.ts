import { create } from 'zustand'
import type { TimelineOutput } from '../types/timeline'
import type { TimelineVersionInfo } from '../types/versions'
import * as editorApi from '../api/editor'
import { getTaskStatus, getProjectStatus } from '../api/status'

export type EditorPhase =
  | 'idle'
  | 'fetching_candidates'
  | 'assembling_scenes'
  | 'stitching'
  | 'reviewing'
  | 'persisting'
  | 'done'

interface EditorStore {
  // Active/latest timeline (polled during generation, loaded on mount)
  timeline: TimelineOutput | null
  taskId: string | null
  isRunning: boolean
  phase: EditorPhase
  error: string | null
  runId: number

  // Version history
  versions: TimelineVersionInfo[]
  selectedVersion: number | null        // null = show active/latest
  viewingTimeline: TimelineOutput | null  // loaded when selectedVersion is set

  // Storyboard version selection for next editor run
  selectedStoryboardVersion: number | null  // null = use latest storyboard

  triggerEditor: (project: string, storyboardVersion?: number | null) => Promise<void>
  fetchTimeline: (project: string) => Promise<void>
  fetchVersions: (project: string) => Promise<void>
  selectVersion: (project: string, version: number | null) => Promise<void>
  setSelectedStoryboardVersion: (version: number | null) => void
  /**
   * Re-hydrate isRunning/taskId/phase from the backend project status.
   * Called on mount to recover a running task after page refresh or tab navigation.
   * Safe to call when already running — skips if isRunning is already true.
   */
  hydrateTaskState: (project: string) => Promise<void>
  pollStatus: (project: string) => Promise<boolean>
  reset: () => void
}

const PHASE_ORDER: EditorPhase[] = [
  'fetching_candidates',
  'assembling_scenes',
  'stitching',
  'reviewing',
  'persisting',
  'done',
]

export function phaseIndex(phase: EditorPhase): number {
  const idx = PHASE_ORDER.indexOf(phase)
  return idx === -1 ? 0 : idx
}

export const PHASE_LABELS: Record<EditorPhase, string> = {
  idle: 'Ready',
  fetching_candidates: 'Fetching candidates...',
  assembling_scenes: 'Assembling scenes...',
  stitching: 'Stitching together...',
  reviewing: 'Reviewing...',
  persisting: 'Saving...',
  done: 'Done',
}

export const useEditorStore = create<EditorStore>((set, get) => ({
  timeline: null,
  taskId: null,
  isRunning: false,
  phase: 'idle',
  error: null,
  runId: 0,
  versions: [],
  selectedVersion: null,
  viewingTimeline: null,
  selectedStoryboardVersion: null,

  triggerEditor: async (project, storyboardVersion) => {
    // Clear taskId immediately so pollStatus won't act on the previous task
    // during the async gap before the new task ID arrives.
    set((s) => ({
      isRunning: true,
      error: null,
      phase: 'fetching_candidates',
      timeline: null,
      taskId: null,
      runId: s.runId + 1,
      selectedVersion: null,
      viewingTimeline: null,
    }))
    try {
      const res = await editorApi.triggerEditor(project, storyboardVersion)
      set({ taskId: res.task_id })
    } catch (e) {
      set({ isRunning: false, error: String(e), phase: 'idle' })
    }
  },

  fetchTimeline: async (project) => {
    try {
      const data = await editorApi.getTimeline(project)
      set({ timeline: data })
    } catch {
      // Not ready yet
    }
  },

  fetchVersions: async (project) => {
    try {
      const versions = await editorApi.getEditorVersions(project)
      set({ versions })
    } catch {
      // Ignore — no versions yet
    }
  },

  selectVersion: async (project, version) => {
    if (version === null) {
      set({ selectedVersion: null, viewingTimeline: null })
      return
    }
    try {
      const data = await editorApi.getTimeline(project, version)
      set({ selectedVersion: version, viewingTimeline: data })
    } catch {
      // Ignore load error
    }
  },

  setSelectedStoryboardVersion: (version) => {
    set({ selectedStoryboardVersion: version })
  },

  hydrateTaskState: async (project) => {
    if (get().isRunning) return
    try {
      const status = await getProjectStatus(project)
      const ed = status.editor
      if (ed.task_id && (ed.celery_state === 'STARTED' || ed.celery_state === 'RETRY')) {
        set({ isRunning: true, taskId: ed.task_id, phase: 'fetching_candidates' })
      }
    } catch {
      // Ignore
    }
  },

  pollStatus: async (project) => {
    const { taskId } = get()
    // No task ID yet — new run is still triggering, keep polling
    if (!taskId) return false
    try {
      const res = await getTaskStatus(taskId)
      if (res.status === 'SUCCESS') {
        set({ isRunning: false, phase: 'done' })
        // Refresh versions list so the new version appears in sidebar
        get().fetchVersions(project)
        return true
      }
      if (res.status === 'FAILURE') {
        set({ isRunning: false, error: res.error ?? 'Editor failed', phase: 'idle' })
        return true
      }
      // Update phase from current_step
      if (res.status === 'STARTED' && res.result) {
        const step = (res.result as Record<string, unknown>).current_step as string | undefined
        if (step && PHASE_ORDER.includes(step as EditorPhase)) {
          set({ phase: step as EditorPhase })
        }
      }
      return false
    } catch {
      return false
    }
  },

  reset: () =>
    set({
      timeline: null,
      taskId: null,
      isRunning: false,
      phase: 'idle',
      error: null,
      runId: 0,
      versions: [],
      selectedVersion: null,
      viewingTimeline: null,
      selectedStoryboardVersion: null,
    }),
}))
