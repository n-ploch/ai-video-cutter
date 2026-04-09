import { useEffect } from 'react'
import { useProjectStore } from '../../stores/projectStore'
import { useStoryboardStore } from '../../stores/storyboardStore'
import { usePolling } from '../../hooks/usePolling'
import ChatInput from './ChatInput'
import BriefTile from './BriefTile'
import StoryTile from './StoryTile'
import SceneTile from './SceneTile'
import UseStoryboardButton from './UseStoryboardButton'
import VersionSidebar from '../common/VersionSidebar'

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
    fetchStoryboard,
    fetchVersions,
    selectVersion,
    startNew,
    pollStatus,
    reset,
  } = useStoryboardStore()

  // Reset on project change, load latest storyboard + version list
  useEffect(() => {
    reset()
    if (currentProject) {
      fetchStoryboard(currentProject)
      fetchVersions(currentProject)
    }
  }, [currentProject, fetchStoryboard, fetchVersions, reset])

  // Poll while running
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

  if (!currentProject) {
    return (
      <div className="flex items-center justify-center h-full text-muted">
        Select or create a project to get started
      </div>
    )
  }

  // What to display: frozen version or active/latest
  const displayedStoryboard = selectedVersion !== null ? viewingStoryboard : storyboard
  const brief = displayedStoryboard?.user_brief ?? submittedBrief

  return (
    <div className="h-full flex overflow-hidden">
      {/* Version history sidebar */}
      <VersionSidebar
        label="Storyboard"
        versions={versions}
        selectedVersion={selectedVersion}
        isActiveRunning={isRunning}
        onSelectVersion={(v) => selectVersion(currentProject, v)}
        onNew={startNew}
      />

      {/* Main content */}
      <div className="flex-1 overflow-auto">
        <div className="max-w-3xl mx-auto px-6 py-4 space-y-4">
          {/* Chat input only when viewing active/latest */}
          {selectedVersion === null && (
            <ChatInput
              onSubmit={handleSubmit}
              disabled={isRunning}
              submitted={!!submittedBrief || !!storyboard}
            />
          )}

          {error && selectedVersion === null && (
            <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-xl text-sm text-red-400">
              {error}
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

          <UseStoryboardButton
            isRunning={isRunning && selectedVersion === null}
            hasStoryboard={!!displayedStoryboard}
            viewedVersion={selectedVersion}
          />
        </div>
      </div>
    </div>
  )
}
