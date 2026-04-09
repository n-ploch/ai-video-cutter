import { useEffect } from 'react'
import { useProjectStore } from '../../stores/projectStore'
import { useStoryboardStore } from '../../stores/storyboardStore'
import { useEditorStore } from '../../stores/editorStore'
import { usePolling } from '../../hooks/usePolling'
import ScenePanel from './ScenePanel'
import StartEditingButton from './StartEditingButton'

export default function EditorPage() {
  const currentProject = useProjectStore((s) => s.currentProject)
  const storyboard = useStoryboardStore((s) => s.storyboard)
  const fetchStoryboard = useStoryboardStore((s) => s.fetchStoryboard)

  const { timeline, isRunning, phase, fetchTimeline, pollStatus, reset } = useEditorStore()

  // Reset and load on project change
  useEffect(() => {
    reset()
    if (currentProject) {
      fetchStoryboard(currentProject)
      fetchTimeline(currentProject)
    }
  }, [currentProject, fetchStoryboard, fetchTimeline, reset])

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
          />
        </div>

        {/* Right: preview placeholder + start button (60%) */}
        <div className="flex-1 flex flex-col gap-4 p-6">
          {/* Preview area */}
          <div className="flex-1 bg-black rounded-xl flex items-center justify-center text-muted text-sm">
            {phase === 'done' && timeline
              ? 'Preview coming in Phase 6'
              : 'Preview will appear after timeline is built'}
          </div>

          {/* Start editing / progress */}
          <StartEditingButton projectName={currentProject} />
        </div>
      </div>

      {/* Bottom: timeline strip placeholder */}
      <div className="h-24 border-t border-border bg-bg-secondary flex items-center px-4">
        {timeline ? (
          <div className="flex gap-1 overflow-x-auto w-full">
            {timeline.scenes.map((scene) => (
              <div
                key={scene.scene_id}
                className="shrink-0 h-14 rounded bg-accent/20 border border-accent/40 flex items-center justify-center px-2"
                style={{
                  width: `${Math.max(60, (scene.total_duration / timeline.total_duration) * 100)}%`,
                  maxWidth: '200px',
                }}
              >
                <span className="text-xs text-accent font-mono truncate">
                  S{scene.scene_id}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-muted">Timeline will appear here after assembly</p>
        )}
      </div>
    </div>
  )
}
