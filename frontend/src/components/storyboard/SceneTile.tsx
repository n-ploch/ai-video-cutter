import type { StoryboardScene } from '../../types/storyboard'
import { useDevMode } from '../../hooks/useDevMode'
import Tag from '../common/Tag'

interface Props {
  scene: StoryboardScene
}

export default function SceneTile({ scene }: Props) {
  const devMode = useDevMode()

  return (
    <div className="p-4 bg-bg-surface rounded-xl space-y-2">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold">Scene {scene.id}</h4>
        <span className="text-xs text-muted">Narration: {scene.narration_segment}</span>
      </div>
      <p className="text-sm text-text-primary/80 leading-relaxed">{scene.scene_description}</p>
      {devMode && scene.reasoning && (
        <div className="p-2 bg-bg-primary rounded text-xs text-muted">
          <strong>Reasoning:</strong> {scene.reasoning}
        </div>
      )}
      <div className="flex flex-wrap gap-1.5">
        {scene.keywords.map((kw) => (
          <Tag key={kw} label={kw} />
        ))}
      </div>
    </div>
  )
}
