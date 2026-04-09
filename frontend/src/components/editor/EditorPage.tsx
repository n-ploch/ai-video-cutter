import { useEffect, useState } from 'react'
import { useProjectStore } from '../../stores/projectStore'
import { useStoryboardStore } from '../../stores/storyboardStore'
import { useEditorStore } from '../../stores/editorStore'
import { usePolling } from '../../hooks/usePolling'
import ScenePanel from './ScenePanel'
import StartEditingButton from './StartEditingButton'
import EditorPreview from './EditorPreview'
import EditorTimeline from './EditorTimeline'
import ExportButton from './ExportButton'
import VersionSidebar from '../common/VersionSidebar'
import type { TimelineVersionInfo } from '../../types/versions'

export default function EditorPage() {
  const currentProject = useProjectStore((s) => s.currentProject)

  // Storyboard (for ScenePanel and version dropdown)
  const storyboard = useStoryboardStore((s) => s.storyboard)
  const storyboardVersions = useStoryboardStore((s) => s.versions)
  const fetchStoryboard = useStoryboardStore((s) => s.fetchStoryboard)
  const fetchStoryboardVersions = useStoryboardStore((s) => s.fetchVersions)

  const {
    timeline,
    isRunning,
    phase,
    runId,
    versions,
    selectedVersion,
    viewingTimeline,
    selectedStoryboardVersion,
    fetchTimeline,
    fetchVersions,
    selectVersion,
    setSelectedStoryboardVersion,
    pollStatus,
    reset,
  } = useEditorStore()

  const [currentSegmentIndex, setCurrentSegmentIndex] = useState(0)

  // Reset and load on project change
  useEffect(() => {
    reset()
    setCurrentSegmentIndex(0)
    if (currentProject) {
      fetchStoryboard(currentProject)
      fetchStoryboardVersions(currentProject)
      fetchTimeline(currentProject)
      fetchVersions(currentProject)
    }
  }, [currentProject, fetchStoryboard, fetchStoryboardVersions, fetchTimeline, fetchVersions, reset])

  // Reset segment index when displayed timeline changes
  const displayedTimeline = selectedVersion !== null ? viewingTimeline : timeline
  useEffect(() => {
    setCurrentSegmentIndex(0)
  }, [displayedTimeline])

  // Poll while running (always, regardless of selectedVersion)
  usePolling(
    async () => {
      if (!currentProject) return
      const done = await pollStatus(currentProject)
      if (done) {
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

  if (!storyboard) {
    return (
      <div className="flex items-center justify-center h-full text-muted">
        Generate a storyboard first before editing
      </div>
    )
  }

  return (
    <div className="h-full flex overflow-hidden">
      {/* Version history sidebar */}
      <VersionSidebar
        label="Timeline"
        versions={versions}
        selectedVersion={selectedVersion}
        isActiveRunning={isRunning}
        onSelectVersion={(v) => selectVersion(currentProject, v)}
        onNew={() => {
          selectVersion(currentProject, null)
        }}
        renderMeta={(v) => {
          const tv = v as TimelineVersionInfo
          return tv.storyboard_version != null ? (
            <span className="text-muted text-xs">sb v{tv.storyboard_version}</span>
          ) : null
        }}
      />

      {/* Main editor layout */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Main area: scene panel + preview */}
        <div className="flex-1 flex min-h-0">
          {/* Left: scene panel */}
          <div className="w-2/5 border-r border-border overflow-hidden">
            <ScenePanel
              storyboard={storyboard}
              timeline={displayedTimeline}
              isRunning={isRunning && selectedVersion === null}
              runId={runId}
            />
          </div>

          {/* Right: preview + controls */}
          <div className="flex-1 flex flex-col gap-4 p-4 min-h-0">
            <div className="flex-1 min-h-0">
              {displayedTimeline ? (
                <EditorPreview
                  project={currentProject}
                  timeline={displayedTimeline}
                  currentIndex={currentSegmentIndex}
                  onIndexChange={setCurrentSegmentIndex}
                />
              ) : (
                <div className="w-full h-full bg-black rounded-xl flex items-center justify-center text-muted text-sm">
                  Preview will appear after timeline is built
                </div>
              )}
            </div>

            {/* Storyboard selector + Start Editing + Export */}
            <div className="space-y-2">
              {/* Storyboard version dropdown */}
              <div className="flex items-center gap-2">
                <label className="text-xs text-muted whitespace-nowrap">Storyboard:</label>
                <select
                  value={selectedStoryboardVersion ?? ''}
                  onChange={(e) => {
                    const val = e.target.value
                    setSelectedStoryboardVersion(val === '' ? null : Number(val))
                  }}
                  disabled={isRunning}
                  className="flex-1 text-xs bg-bg-secondary border border-border rounded-lg px-2 py-1.5 text-foreground disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <option value="">Latest</option>
                  {[...storyboardVersions]
                    .sort((a, b) => b.version - a.version)
                    .map((v) => (
                      <option key={v.version} value={v.version}>
                        v{v.version}
                        {v.brief_snippet ? ` — ${v.brief_snippet.slice(0, 40)}` : ''}
                      </option>
                    ))}
                </select>
              </div>

              <div className="flex items-center gap-3">
                <div className="flex-1">
                  <StartEditingButton
                    projectName={currentProject}
                    storyboardVersion={selectedStoryboardVersion}
                  />
                </div>
                {phase === 'done' && displayedTimeline && selectedVersion === null && (
                  <ExportButton projectName={currentProject} />
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Bottom: interactive timeline (full width, fixed height) */}
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
