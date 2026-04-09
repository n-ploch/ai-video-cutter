import { create } from 'zustand'
import type { TimelineOutput } from '../types/timeline'
import * as editorApi from '../api/editor'
import { getTaskStatus } from '../api/status'

export type EditorPhase =
  | 'idle'
  | 'fetching_candidates'
  | 'assembling_scenes'
  | 'stitching'
  | 'reviewing'
  | 'persisting'
  | 'done'

interface EditorStore {
  timeline: TimelineOutput | null
  taskId: string | null
  isRunning: boolean
  phase: EditorPhase
  error: string | null

  triggerEditor: (project: string) => Promise<void>
  fetchTimeline: (project: string) => Promise<void>
  pollStatus: () => Promise<boolean>
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

  triggerEditor: async (project) => {
    set({ isRunning: true, error: null, phase: 'fetching_candidates', timeline: null })
    try {
      const res = await editorApi.triggerEditor(project)
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

  pollStatus: async () => {
    const { taskId } = get()
    if (!taskId) return true
    try {
      const res = await getTaskStatus(taskId)
      if (res.status === 'SUCCESS') {
        set({ isRunning: false, phase: 'done' })
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
    }),
}))
