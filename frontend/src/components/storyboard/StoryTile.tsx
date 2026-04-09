interface Props {
  story: string
  score?: number | null
}

export default function StoryTile({ story, score }: Props) {
  return (
    <div className="p-4 bg-bg-surface rounded-xl space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted font-medium">Story</p>
        {score != null && (
          <span className="text-xs text-accent tabular-nums">
            Score: {(score * 100).toFixed(0)}%
          </span>
        )}
      </div>
      <div className="text-sm text-text-primary/80 leading-relaxed whitespace-pre-line">
        {story}
      </div>
    </div>
  )
}
