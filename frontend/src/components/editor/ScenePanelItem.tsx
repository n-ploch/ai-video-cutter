import { useState } from 'react'
import { ChevronDown, ChevronRight, Loader2 } from 'lucide-react'
import type { SceneTimeline } from '../../types/timeline'
import type { StoryboardScene } from '../../types/storyboard'
import { formatDuration } from '../../utils/formatting'

interface Props {
  storyboardScene: StoryboardScene
  timelineScene: SceneTimeline | undefined
  isRunning: boolean
}

export default function ScenePanelItem({ storyboardScene, timelineScene, isRunning }: Props) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="bg-bg-secondary rounded-xl border border-border overflow-hidden">
      <div
        className="flex items-start gap-3 p-3 cursor-pointer hover:bg-bg-primary/40 transition-colors"
        onClick={() => timelineScene && setExpanded((v) => !v)}
      >
        <span className="mt-0.5 text-xs font-mono text-muted w-5 text-right shrink-0">
          {storyboardScene.id}
        </span>

        <div className="flex-1 min-w-0">
          <p className="text-sm text-foreground leading-snug line-clamp-2">
            {storyboardScene.scene_description}
          </p>
          {timelineScene && (
            <p className="text-xs text-muted mt-1">
              {timelineScene.entries.length} segments &middot;{' '}
              {formatDuration(timelineScene.total_duration)}
            </p>
          )}
        </div>

        <div className="shrink-0">
          {isRunning && !timelineScene ? (
            <Loader2 size={14} className="animate-spin text-muted" />
          ) : timelineScene ? (
            expanded ? (
              <ChevronDown size={14} className="text-muted" />
            ) : (
              <ChevronRight size={14} className="text-muted" />
            )
          ) : null}
        </div>
      </div>

      {expanded && timelineScene && (
        <div className="border-t border-border">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-muted border-b border-border">
                <th className="text-left px-3 py-2 font-medium">#</th>
                <th className="text-left px-3 py-2 font-medium">Segment</th>
                <th className="text-left px-3 py-2 font-medium">Dur</th>
                <th className="text-left px-3 py-2 font-medium">Quality</th>
              </tr>
            </thead>
            <tbody>
              {timelineScene.entries.map((entry) => (
                <tr key={entry.position} className="border-b border-border/50 last:border-0">
                  <td className="px-3 py-1.5 text-muted font-mono">{entry.position + 1}</td>
                  <td className="px-3 py-1.5 text-foreground font-mono truncate max-w-[120px]">
                    {entry.segment_id}
                  </td>
                  <td className="px-3 py-1.5 text-muted">{formatDuration(entry.duration)}</td>
                  <td className="px-3 py-1.5">
                    <span
                      className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                        entry.quality_rating === 'excellent'
                          ? 'bg-green-500/20 text-green-400'
                          : entry.quality_rating === 'good'
                            ? 'bg-blue-500/20 text-blue-400'
                            : 'bg-muted/20 text-muted'
                      }`}
                    >
                      {entry.quality_rating}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
