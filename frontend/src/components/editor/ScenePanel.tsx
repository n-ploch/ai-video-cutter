import type { StoryboardOutput } from '../../types/storyboard'
import type { TimelineOutput } from '../../types/timeline'
import ScenePanelItem from './ScenePanelItem'

interface Props {
  storyboard: StoryboardOutput
  timeline: TimelineOutput | null
  isRunning: boolean
  runId: number
}

export default function ScenePanel({ storyboard, timeline, isRunning, runId }: Props) {
  const sceneMap = new Map(timeline?.scenes.map((s) => [s.scene_id, s]) ?? [])

  return (
    <div className="h-full flex flex-col">
      <div className="px-4 py-3 border-b border-border shrink-0">
        <h2 className="text-sm font-semibold text-foreground">Scenes</h2>
        {timeline && (
          <p className="text-xs text-muted mt-0.5">
            {timeline.total_segments} segments &middot;{' '}
            {Math.round(timeline.total_duration)}s total
          </p>
        )}
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {storyboard.scenes.map((scene) => (
          <ScenePanelItem
            key={`${scene.id}-${runId}`}
            storyboardScene={scene}
            timelineScene={sceneMap.get(scene.id)}
            isRunning={isRunning}
          />
        ))}
      </div>
    </div>
  )
}
