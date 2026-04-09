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

export default function EditorPage() {
  const currentProject = useProjectStore((s) => s.currentProject)
  const storyboard = useStoryboardStore((s) => s.storyboard)
  const fetchStoryboard = useStoryboardStore((s) => s.fetchStoryboard)

  const { timeline, isRunning, phase, runId, fetchTimeline, pollStatus, reset } = useEditorStore()

  const [currentSegmentIndex, setCurrentSegmentIndex] = useState(0)

  // Reset and load on project change
  useEffect(() => {
    reset()
    setCurrentSegmentIndex(0)
    if (currentProject) {
      fetchStoryboard(currentProject)
      fetchTimeline(currentProject)
    }
  }, [currentProject, fetchStoryboard, fetchTimeline, reset])

  // Reset segment index when timeline loads
  useEffect(() => {
    setCurrentSegmentIndex(0)
  }, [timeline])

  // Poll while running
  usePolling(
    async () => {
      const done = await pollStatus()
      if (done && currentProject) {
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
    <div className="h-full flex flex-col">
      {/* Main area: scene panel + preview */}
      <div className="flex-1 flex min-h-0">
        {/* Left: scene panel (40%) */}
        <div className="w-2/5 border-r border-border overflow-hidden">
          <ScenePanel
            storyboard={storyboard}
            timeline={timeline}
            isRunning={isRunning}
            runId={runId}
          />
        </div>

        {/* Right: preview + start button (60%) */}
        <div className="flex-1 flex flex-col gap-4 p-4 min-h-0">
          <div className="flex-1 min-h-0">
            {timeline ? (
              <EditorPreview
                project={currentProject}
                timeline={timeline}
                currentIndex={currentSegmentIndex}
                onIndexChange={setCurrentSegmentIndex}
              />
            ) : (
              <div className="w-full h-full bg-black rounded-xl flex items-center justify-center text-muted text-sm">
                Preview will appear after timeline is built
              </div>
            )}
          </div>

          <div className="flex items-center gap-3">
            <div className="flex-1">
              <StartEditingButton projectName={currentProject} />
            </div>
            {phase === 'done' && timeline && (
              <ExportButton projectName={currentProject} />
            )}
          </div>
        </div>
      </div>

      {/* Bottom: interactive timeline (full width, fixed height) */}
      <div className="h-20 border-t border-border bg-bg-secondary shrink-0">
        {timeline ? (
          <EditorTimeline
            timeline={timeline}
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
  )
}
