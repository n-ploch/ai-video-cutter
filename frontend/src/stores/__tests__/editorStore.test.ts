import { describe, it, expect, vi, beforeEach } from 'vitest'
import { phaseIndex, PHASE_LABELS, useEditorStore, type EditorPhase } from '../editorStore'

// Mock the API modules so the store can be imported without a real backend
vi.mock('../../api/editor', () => ({
  triggerEditor: vi.fn(),
  getTimeline: vi.fn(),
  getEditorVersions: vi.fn().mockResolvedValue([]),
}))
vi.mock('../../api/status', () => ({
  getTaskStatus: vi.fn(),
}))

import * as editorApi from '../../api/editor'
import * as statusApi from '../../api/status'

describe('phaseIndex', () => {
  it('returns 0 for idle (not in active phase order)', () => {
    expect(phaseIndex('idle')).toBe(0)
  })

  it('returns correct index for active phases', () => {
    expect(phaseIndex('fetching_candidates')).toBe(0)
    expect(phaseIndex('assembling_scenes')).toBe(1)
    expect(phaseIndex('stitching')).toBe(2)
    expect(phaseIndex('reviewing')).toBe(3)
    expect(phaseIndex('persisting')).toBe(4)
    expect(phaseIndex('done')).toBe(5)
  })
})

describe('PHASE_LABELS', () => {
  it('has a label for every EditorPhase', () => {
    const allPhases: EditorPhase[] = [
      'idle',
      'fetching_candidates',
      'assembling_scenes',
      'stitching',
      'reviewing',
      'persisting',
      'done',
    ]
    for (const phase of allPhases) {
      expect(PHASE_LABELS[phase]).toBeDefined()
      expect(typeof PHASE_LABELS[phase]).toBe('string')
      expect(PHASE_LABELS[phase].length).toBeGreaterThan(0)
    }
  })
})

describe('editorStore', () => {
  beforeEach(() => {
    useEditorStore.getState().reset()
    vi.clearAllMocks()
  })

  it('starts in idle state', () => {
    const state = useEditorStore.getState()
    expect(state.phase).toBe('idle')
    expect(state.isRunning).toBe(false)
    expect(state.taskId).toBeNull()
    expect(state.timeline).toBeNull()
    expect(state.runId).toBe(0)
  })

  it('triggerEditor sets isRunning, clears taskId/timeline, increments runId', async () => {
    vi.mocked(editorApi.triggerEditor).mockResolvedValue({
      task_id: 'task-123',
      status: 'PENDING',
      result: null,
      error: null,
    })

    await useEditorStore.getState().triggerEditor('my_project')

    const state = useEditorStore.getState()
    expect(state.isRunning).toBe(true)
    expect(state.taskId).toBe('task-123')
    expect(state.timeline).toBeNull()
    expect(state.runId).toBe(1)
    expect(state.phase).toBe('fetching_candidates')
  })

  it('triggerEditor sets error on failure', async () => {
    vi.mocked(editorApi.triggerEditor).mockRejectedValue(new Error('Network error'))

    await useEditorStore.getState().triggerEditor('my_project')

    const state = useEditorStore.getState()
    expect(state.isRunning).toBe(false)
    expect(state.phase).toBe('idle')
    expect(state.error).toContain('Network error')
  })

  it('pollStatus returns false (keep polling) when taskId is null', async () => {
    const done = await useEditorStore.getState().pollStatus('my_project')
    expect(done).toBe(false)
  })

  it('pollStatus updates phase from current_step on STARTED status', async () => {
    useEditorStore.setState({ taskId: 'task-123', isRunning: true })

    vi.mocked(statusApi.getTaskStatus).mockResolvedValue({
      task_id: 'task-123',
      status: 'STARTED',
      result: { current_step: 'assembling_scenes' },
      error: null,
    })

    const done = await useEditorStore.getState().pollStatus('my_project')

    expect(done).toBe(false)
    expect(useEditorStore.getState().phase).toBe('assembling_scenes')
  })

  it('pollStatus sets done=true and phase=done on SUCCESS', async () => {
    useEditorStore.setState({ taskId: 'task-123', isRunning: true })

    vi.mocked(statusApi.getTaskStatus).mockResolvedValue({
      task_id: 'task-123',
      status: 'SUCCESS',
      result: { status: 'complete' },
      error: null,
    })

    const done = await useEditorStore.getState().pollStatus('my_project')

    expect(done).toBe(true)
    expect(useEditorStore.getState().phase).toBe('done')
    expect(useEditorStore.getState().isRunning).toBe(false)
  })

  it('pollStatus sets error and stops on FAILURE', async () => {
    useEditorStore.setState({ taskId: 'task-123', isRunning: true })

    vi.mocked(statusApi.getTaskStatus).mockResolvedValue({
      task_id: 'task-123',
      status: 'FAILURE',
      result: null,
      error: 'Out of memory',
    })

    const done = await useEditorStore.getState().pollStatus('my_project')

    expect(done).toBe(true)
    expect(useEditorStore.getState().isRunning).toBe(false)
    expect(useEditorStore.getState().error).toBe('Out of memory')
    expect(useEditorStore.getState().phase).toBe('idle')
  })

  it('reset clears all state', async () => {
    useEditorStore.setState({
      taskId: 'task-123',
      isRunning: true,
      phase: 'stitching',
      error: 'oops',
      runId: 5,
    })

    useEditorStore.getState().reset()

    const state = useEditorStore.getState()
    expect(state.taskId).toBeNull()
    expect(state.isRunning).toBe(false)
    expect(state.phase).toBe('idle')
    expect(state.error).toBeNull()
    expect(state.runId).toBe(0)
  })

  it('re-trigger increments runId and clears stale taskId before API returns', async () => {
    // Simulate a slow API call — we check state before it resolves
    let resolveFirst: (v: unknown) => void
    vi.mocked(editorApi.triggerEditor).mockReturnValue(
      new Promise((res) => { resolveFirst = res }),
    )

    useEditorStore.setState({ taskId: 'old-task', phase: 'done', runId: 1 })

    const trigger = useEditorStore.getState().triggerEditor('my_project')

    // During the async gap the old taskId must be cleared
    expect(useEditorStore.getState().taskId).toBeNull()
    expect(useEditorStore.getState().runId).toBe(2)

    resolveFirst!({ task_id: 'new-task', status: 'PENDING', result: null, error: null })
    await trigger

    expect(useEditorStore.getState().taskId).toBe('new-task')
  })
})
