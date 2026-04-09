import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { useProjectStore } from '../../stores/projectStore'
import { useStoryboardStore } from '../../stores/storyboardStore'
import { useEditorStore, PHASE_LABELS, phaseIndex, type EditorPhase } from '../../stores/editorStore'
import { usePolling } from '../../hooks/usePolling'
import { getStoryboard } from '../../api/storyboard'
import ScenePanel from './ScenePanel'
import EditorPreview from './EditorPreview'
import EditorTimeline from './EditorTimeline'
import ExportButton from './ExportButton'
import EditorVersionSidebar from './EditorVersionSidebar'
import type { StoryboardOutput } from '../../types/storyboard'

const ACTIVE_PHASES: EditorPhase[] = [
  'fetching_candidates',
  'assembling_scenes',
  'stitching',
  'reviewing',
  'persisting',
]

export default function EditorPage() {
  const currentProject = useProjectStore((s) => s.currentProject)

  // Storyboard store — latest storyboard + version list for the dropdown
  const latestStoryboard = useStoryboardStore((s) => s.storyboard)
  const storyboardVersions = useStoryboardStore((s) => s.versions)
  const fetchStoryboard = useStoryboardStore((s) => s.fetchStoryboard)
  const fetchStoryboardVersions = useStoryboardStore((s) => s.fetchVersions)

  const {
    timeline,
    isRunning,
    phase,
    error,
    runId,
    versions,
    selectedVersion,
    viewingTimeline,
    selectedStoryboardVersion,
    fetchVersions,
    selectVersion,
    setSelectedStoryboardVersion,
    hydrateTaskState,
    triggerEditor,
    pollStatus,
    reset,
  } = useEditorStore()

  const [currentSegmentIndex, setCurrentSegmentIndex] = useState(0)
  // Storyboard shown in ScenePanel — tracks selectedStoryboardVersion dropdown
  const [activeStoryboard, setActiveStoryboard] = useState<StoryboardOutput | null>(null)

  // On project change: reset to "create new" default, load versions + storyboard data
  useEffect(() => {
    reset()
    setCurrentSegmentIndex(0)
    setActiveStoryboard(null)
    if (currentProject) {
      // Load storyboard data for the scene panel (not fetchTimeline — default is create new)
      fetchStoryboard(currentProject)
      fetchStoryboardVersions(currentProject)
      fetchVersions(currentProject)
      hydrateTaskState(currentProject)
    }
  }, [currentProject, fetchStoryboard, fetchStoryboardVersions, fetchVersions, hydrateTaskState, reset])

  // Load the correct storyboard when the dropdown selection changes
  useEffect(() => {
    if (!currentProject) return
    if (selectedStoryboardVersion === null) {
      setActiveStoryboard(null)  // falls back to latestStoryboard
      return
    }
    getStoryboard(currentProject, selectedStoryboardVersion)
      .then(setActiveStoryboard)
      .catch(() => setActiveStoryboard(null))
  }, [currentProject, selectedStoryboardVersion])

  const displayedTimeline = selectedVersion !== null ? viewingTimeline : timeline
  const displayedStoryboard = activeStoryboard ?? latestStoryboard

  useEffect(() => {
    setCurrentSegmentIndex(0)
  }, [displayedTimeline])

  // Poll while running — auto-starts after hydrateTaskState sets isRunning
  usePolling(
    async () => {
      if (!currentProject) return
      const done = await pollStatus(currentProject)
      if (done) {
        // Fetch the newly completed timeline into the active slot
        const { fetchTimeline } = useEditorStore.getState()
        fetchTimeline(currentProject)
      }
    },
    3000,
    !isRunning,
  )

  if (!currentProject) {
    return (
      <div className="flex items-center justify-center h-full text-muted">
        Select or create a project to get started
      </div>
    )
  }

  const isViewingPast = selectedVersion !== null
  // Active finished = not viewing past, not running, and a completed timeline is loaded
  const isActiveFinished = !isViewingPast && !isRunning && timeline !== null
  const currentPhaseIdx = phaseIndex(phase)

  return (
    <div className="h-full flex overflow-hidden">
      <EditorVersionSidebar
        versions={versions}
        selectedVersion={selectedVersion}
        isRunning={isRunning}
        onCreateNew={() => selectVersion(currentProject, null)}
        onSelectVersion={(v) => selectVersion(currentProject, v)}
      />

      <div className="flex-1 flex flex-col min-w-0">

        {/* ── Top bar: storyboard selector + action ── */}
        <div className="shrink-0 border-b border-border bg-bg-secondary px-4 py-3 flex items-center gap-3">
          <div className="flex items-center gap-2 min-w-0">
            <label className="text-xs text-muted whitespace-nowrap">Storyboard</label>
            <select
              value={selectedStoryboardVersion ?? ''}
              onChange={(e) => {
                const val = e.target.value
                setSelectedStoryboardVersion(val === '' ? null : Number(val))
              }}
              disabled={isRunning || isViewingPast}
              className="text-xs bg-bg-primary border border-border rounded-lg px-2 py-1.5 text-foreground disabled:opacity-50 disabled:cursor-not-allowed min-w-0 max-w-xs"
            >
              <option value="">Latest</option>
              {[...storyboardVersions]
                .sort((a, b) => b.version - a.version)
                .map((v) => (
                  <option key={v.version} value={v.version}>
                    v{v.version}{v.brief_snippet ? ` — ${v.brief_snippet.slice(0, 50)}` : ''}
                  </option>
                ))}
            </select>
          </div>

          <div className="flex-1" />

          {/* Action area — right side of top bar */}
          {isViewingPast || isActiveFinished ? (
            <div className="flex items-center gap-3">
              <div className="px-4 py-1.5 bg-green-500/20 border border-green-500/30 rounded-lg text-sm text-green-400 font-medium">
                Timeline ready
              </div>
              <ExportButton projectName={currentProject} />
            </div>
          ) : isRunning ? (
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2 text-sm text-foreground">
                <Loader2 size={14} className="animate-spin text-accent shrink-0" />
                <span>{PHASE_LABELS[phase]}</span>
              </div>
              <div className="flex gap-0.5">
                {ACTIVE_PHASES.map((p, i) => (
                  <div
                    key={p}
                    title={p}
                    className={`w-6 h-1.5 rounded-full transition-colors ${
                      i < currentPhaseIdx
                        ? 'bg-accent'
                        : i === currentPhaseIdx
                          ? 'bg-accent/60'
                          : 'bg-border'
                    }`}
                  />
                ))}
              </div>
            </div>
          ) : error ? (
            <div className="flex items-center gap-3">
              <span className="text-xs text-red-400 max-w-xs truncate">{error}</span>
              <button
                onClick={() => triggerEditor(currentProject, selectedStoryboardVersion)}
                className="px-4 py-1.5 bg-accent text-white text-sm font-medium rounded-lg hover:bg-accent/90 transition-colors"
              >
                Retry
              </button>
            </div>
          ) : (
            <button
              onClick={() => triggerEditor(currentProject, selectedStoryboardVersion)}
              disabled={!displayedStoryboard}
              className="px-4 py-1.5 bg-accent text-white text-sm font-medium rounded-lg hover:bg-accent/90 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Start Editing
            </button>
          )}
        </div>

        {/* ── Main area: scene panel + preview ── */}
        <div className="flex-1 flex min-h-0">
          <div className="w-2/5 border-r border-border overflow-hidden">
            {displayedStoryboard ? (
              <ScenePanel
                storyboard={displayedStoryboard}
                timeline={displayedTimeline}
                isRunning={isRunning && !isViewingPast}
                runId={runId}
              />
            ) : (
              <div className="flex items-center justify-center h-full text-muted text-sm">
                Generate a storyboard first
              </div>
            )}
          </div>

          <div className="flex-1 flex flex-col p-4 min-h-0">
            {displayedTimeline ? (
              <EditorPreview
                project={currentProject}
                timeline={displayedTimeline}
                currentIndex={currentSegmentIndex}
                onIndexChange={setCurrentSegmentIndex}
              />
            ) : (
              <div className="w-full h-full bg-black rounded-xl flex items-center justify-center text-muted text-sm">
                {isRunning ? 'Building timeline…' : 'Preview will appear after timeline is built'}
              </div>
            )}
          </div>
        </div>

        {/* ── Bottom: interactive timeline ── */}
        <div className="h-20 border-t border-border bg-bg-secondary shrink-0">
          {displayedTimeline ? (
            <EditorTimeline
              timeline={displayedTimeline}
              currentIndex={currentSegmentIndex}
              onIndexChange={setCurrentSegmentIndex}
            />
          ) : (
            <div className="flex items-center justify-center h-full">
              <p className="text-xs text-muted">Timeline will appear here after assembly</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
