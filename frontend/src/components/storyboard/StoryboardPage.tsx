import { useEffect } from 'react'
import { useProjectStore } from '../../stores/projectStore'
import { useStoryboardStore } from '../../stores/storyboardStore'
import { usePolling } from '../../hooks/usePolling'
import ChatInput from './ChatInput'
import BriefTile from './BriefTile'
import StoryTile from './StoryTile'
import SceneTile from './SceneTile'
import UseStoryboardButton from './UseStoryboardButton'

export default function StoryboardPage() {
  const currentProject = useProjectStore((s) => s.currentProject)
  const {
    storyboard,
    isRunning,
    error,
    submittedBrief,
    triggerStoryboard,
    fetchStoryboard,
    pollStatus,
    reset,
  } = useStoryboardStore()

  // Reset on project change
  useEffect(() => {
    reset()
    if (currentProject) {
      // Try to load existing storyboard
      fetchStoryboard(currentProject)
    }
  }, [currentProject, fetchStoryboard, reset])

  // Poll while running
  usePolling(
    async () => {
      const done = await pollStatus()
      if (done && currentProject) {
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

  const brief = storyboard?.user_brief ?? submittedBrief

  return (
    <div className="h-full overflow-auto">
      <div className="max-w-3xl mx-auto px-6 py-4 space-y-4">
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

        {brief && <BriefTile brief={brief} />}

        {storyboard && (
          <>
            <StoryTile
              story={storyboard.story}
              score={storyboard.story_judge_result?.total_score}
            />
            <div className="space-y-3">
              <p className="text-xs text-muted font-medium">
                Scenes ({storyboard.scenes.length})
              </p>
              {storyboard.scenes.map((scene) => (
                <SceneTile key={scene.id} scene={scene} />
              ))}
            </div>
          </>
        )}

        <UseStoryboardButton
          isRunning={isRunning}
          hasStoryboard={!!storyboard}
        />
      </div>
    </div>
  )
}
