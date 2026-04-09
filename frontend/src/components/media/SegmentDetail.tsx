import type { SegmentBase, SegmentDescription } from '../../types/segment'
import { useDevMode } from '../../hooks/useDevMode'
import Tag from '../common/Tag'

interface Props {
  segment: SegmentBase
  description: SegmentDescription | undefined
  onSeek: (time: number) => void
}

export default function SegmentDetail({ segment, description, onSeek }: Props) {
  const devMode = useDevMode()
  const duration = segment.end - segment.start

  return (
    <div className="mt-4 p-4 bg-bg-surface rounded-xl space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">
          Segment {segment.segment_id}
        </h3>
        <span className="text-xs text-muted tabular-nums">
          {segment.start.toFixed(1)}s – {segment.end.toFixed(1)}s ({duration.toFixed(1)}s)
        </span>
      </div>

      {/* Description */}
      {description && (
        <p className="text-sm text-text-primary/80 leading-relaxed">
          {description.description}
        </p>
      )}

      {/* Segment sub-timeline with highlights */}
      {description && description.highlights.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs text-muted font-medium">Highlights</p>
          <div className="relative h-6 bg-bg-primary rounded overflow-hidden">
            {description.highlights.map((hl, i) => {
              const hlStart = parseTimestamp(hl.start)
              const hlEnd = parseTimestamp(hl.end)
              const left = ((hlStart - segment.start) / duration) * 100
              const width = ((hlEnd - hlStart) / duration) * 100
              return (
                <div
                  key={i}
                  className="absolute top-0 h-full bg-accent/40 hover:bg-accent/70 cursor-pointer transition-colors group"
                  style={{ left: `${Math.max(0, left)}%`, width: `${Math.max(width, 1)}%` }}
                  onClick={() => onSeek(hlStart)}
                >
                  <div className="absolute bottom-full mb-1 left-1/2 -translate-x-1/2 hidden group-hover:block bg-bg-surface text-text-primary text-xs p-2 rounded shadow-lg whitespace-nowrap z-30 max-w-xs">
                    {hl.description}
                  </div>
                </div>
              )
            })}

            {/* Movement markers */}
            {segment.camera_movements.map((mv) => {
              const pos = ((mv.start_time - segment.start) / duration) * 100
              return (
                <div
                  key={mv.movement_id}
                  className="absolute top-0 h-full w-px bg-muted/50"
                  style={{ left: `${Math.max(0, pos)}%` }}
                  title={`Movement ${mv.movement_id}`}
                />
              )
            })}
          </div>
        </div>
      )}

      {/* Technical specs */}
      {description?.technical_specs && (
        <div className="space-y-1">
          <p className="text-xs text-muted font-medium">Technical Specs</p>
          <div className="flex gap-4 text-sm">
            <Spec label="Framing" value={description.technical_specs.framing} />
            <Spec label="Movement" value={description.technical_specs.movement} />
            <Spec label="Angle" value={description.technical_specs.angle} />
          </div>
          {devMode && description.technical_specs.reasoning && (
            <div className="mt-2 p-2 bg-bg-primary rounded text-xs text-muted space-y-1">
              <p><strong>Framing:</strong> {description.technical_specs.reasoning.framing}</p>
              <p><strong>Movement:</strong> {description.technical_specs.reasoning.movement}</p>
              <p><strong>Angle:</strong> {description.technical_specs.reasoning.angle}</p>
            </div>
          )}
        </div>
      )}

      {/* Quality score */}
      {description?.quality_score && (
        <div className="space-y-1">
          <p className="text-xs text-muted font-medium">Quality</p>
          <QualityBadge rating={description.quality_score.rating} />
          {devMode && (
            <p className="text-xs text-muted mt-1">{description.quality_score.reasoning}</p>
          )}
        </div>
      )}

      {/* Tags */}
      {description && description.segment_tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {description.segment_tags.map((tag) => (
            <Tag key={tag} label={tag} />
          ))}
        </div>
      )}
    </div>
  )
}

function Spec({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-muted text-xs">{label}</span>
      <p className="text-text-primary">{value}</p>
    </div>
  )
}

function QualityBadge({ rating }: { rating: string }) {
  const colors: Record<string, string> = {
    excellent: 'bg-green-500/20 text-green-400',
    good: 'bg-blue-500/20 text-blue-400',
    medium: 'bg-yellow-500/20 text-yellow-400',
    bad: 'bg-red-500/20 text-red-400',
  }
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${colors[rating] ?? colors.good}`}>
      {rating}
    </span>
  )
}

/** Parse "HH:MM:SS.mmm" or "MM:SS.mmm" to seconds */
function parseTimestamp(ts: string): number {
  const parts = ts.split(':')
  if (parts.length === 3) {
    return parseFloat(parts[0]) * 3600 + parseFloat(parts[1]) * 60 + parseFloat(parts[2])
  }
  if (parts.length === 2) {
    return parseFloat(parts[0]) * 60 + parseFloat(parts[1])
  }
  return parseFloat(ts) || 0
}
