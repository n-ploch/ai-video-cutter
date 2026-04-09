import { useEffect } from 'react'
import { useProjectStore } from '../../stores/projectStore'
import { useStoryboardStore } from '../../stores/storyboardStore'
import { usePolling } from '../../hooks/usePolling'
import ChatInput from './ChatInput'
import BriefTile from './BriefTile'
import StoryTile from './StoryTile'
import SceneTile from './SceneTile'
import UseStoryboardButton from './UseStoryboardButton'
import StoryboardVersionSidebar from './StoryboardVersionSidebar'

export default function StoryboardPage() {
  const currentProject = useProjectStore((s) => s.currentProject)
  const {
    storyboard,
    isRunning,
    error,
    submittedBrief,
    versions,
    selectedVersion,
    viewingStoryboard,
    triggerStoryboard,
    fetchVersions,
    hydrateTaskState,
    selectVersion,
    startNew,
    pollStatus,
    reset,
  } = useStoryboardStore()

  // On project change: reset, load version list, recover any active task.
  // fetchStoryboard is intentionally NOT called here — the default view is
  // the blank "create new" chat interface.  Past versions are loaded on demand
  // when the user clicks one in the sidebar.
  useEffect(() => {
    reset()
    if (currentProject) {
      fetchVersions(currentProject)
      hydrateTaskState(currentProject)
    }
  }, [currentProject, fetchVersions, hydrateTaskState, reset])

  // Poll while a task is running — automatically starts/stops as isRunning changes.
  // usePolling re-runs its effect whenever shouldStop changes, so hydrating
  // isRunning from false → true (page refresh) will start polling immediately.
  usePolling(
    async () => {
      if (!currentProject) return
      const done = await pollStatus(currentProject)
      if (done) {
        fetchStoryboard(currentProject)
      }
    },
    3000,
    !isRunning,
  )

  const handleSubmit = (brief: string) => {
    if (!currentProject) return
    triggerStoryboard(currentProject, brief)
  }

  const handleCreateNew = () => {
    startNew()
    // selectVersion sets selectedVersion = null and clears viewingStoryboard
    // startNew already does this, but calling it ensures the sidebar deselects
  }

  const handleSelectVersion = (v: number | null) => {
    if (!currentProject) return
    if (v === null) {
      // Return to active view without clearing active state
      selectVersion(currentProject, null)
    } else {
      selectVersion(currentProject, v)
    }
  }

  if (!currentProject) {
    return (
      <div className="flex items-center justify-center h-full text-muted">
        Select or create a project to get started
      </div>
    )
  }

  // What to display in the main content area
  const isActiveView = selectedVersion === null
  const displayedStoryboard = isActiveView ? storyboard : viewingStoryboard
  const brief = displayedStoryboard?.user_brief ?? (isActiveView ? submittedBrief : null)

  return (
    <div className="h-full flex overflow-hidden">
      <StoryboardVersionSidebar
        versions={versions}
        selectedVersion={selectedVersion}
        isRunning={isRunning}
        onCreateNew={handleCreateNew}
        onSelectVersion={handleSelectVersion}
      />

      <div className="flex-1 overflow-auto">
        <div className="max-w-3xl mx-auto px-6 py-4 space-y-4">

          {isActiveView ? (
            // ── Active view: chat input + live generation progress ──
            <>
              <ChatInput
                onSubmit={handleSubmit}
                disabled={isRunning}
                submitted={!!submittedBrief || !!storyboard}
              />

              {error && (
                <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-xl text-sm text-red-400">
                  {error}
                </div>
              )}
            </>
          ) : (
            // ── Past version view: read-only header ──
            <div className="flex items-center gap-2 py-2 text-sm text-muted">
              <span className="font-mono font-semibold text-foreground">
                v{selectedVersion}
              </span>
              <span>— read-only</span>
            </div>
          )}

          {brief && <BriefTile brief={brief} />}

          {displayedStoryboard && (
            <>
              <StoryTile
                story={displayedStoryboard.story}
                score={displayedStoryboard.story_judge_result?.total_score}
              />
              <div className="space-y-3">
                <p className="text-xs text-muted font-medium">
                  Scenes ({displayedStoryboard.scenes.length})
                </p>
                {displayedStoryboard.scenes.map((scene) => (
                  <SceneTile key={scene.id} scene={scene} />
                ))}
              </div>
            </>
          )}

          {/* Use Storyboard button — shown whenever there's content to use */}
          {displayedStoryboard && (
            <UseStoryboardButton
              isRunning={isRunning && isActiveView}
              hasStoryboard={!!displayedStoryboard}
              viewedVersion={selectedVersion}
            />
          )}
        </div>
      </div>
    </div>
  )
}
