import type { SegmentBase } from '../../types/segment'

interface Props {
  segments: SegmentBase[]
  videoDuration: number
  currentTime: number
  selectedSegmentId: string | null
  onSelectSegment: (id: string) => void
}

const SEGMENT_COLORS = [
  'bg-accent',
  'bg-blue-500',
  'bg-emerald-500',
  'bg-purple-500',
  'bg-yellow-500',
  'bg-pink-500',
  'bg-cyan-500',
  'bg-orange-400',
]

export default function SegmentTimeline({
  segments,
  videoDuration,
  currentTime,
  selectedSegmentId,
  onSelectSegment,
}: Props) {
  if (!segments.length || videoDuration <= 0) return null

  const playheadPercent = (currentTime / videoDuration) * 100

  return (
    <div className="relative mt-3">
      {/* Track */}
      <div className="relative h-8 bg-bg-primary rounded-lg overflow-hidden">
        {segments.map((seg, i) => {
          const left = (seg.start / videoDuration) * 100
          const width = ((seg.end - seg.start) / videoDuration) * 100
          const isSelected = seg.segment_id === selectedSegmentId
          const color = SEGMENT_COLORS[i % SEGMENT_COLORS.length]

          return (
            <button
              key={seg.segment_id}
              title={`${seg.segment_id} (${seg.start.toFixed(1)}s – ${seg.end.toFixed(1)}s)`}
              onClick={() => onSelectSegment(seg.segment_id)}
              className={`absolute top-0 h-full transition-opacity cursor-pointer ${color} ${
                isSelected ? 'opacity-100 ring-2 ring-white/50 z-10' : 'opacity-60 hover:opacity-80'
              }`}
              style={{ left: `${left}%`, width: `${Math.max(width, 0.5)}%` }}
            />
          )
        })}

        {/* Playhead */}
        <div
          className="absolute top-0 h-full w-0.5 bg-white z-20 pointer-events-none"
          style={{ left: `${Math.min(playheadPercent, 100)}%` }}
        />
      </div>

      {/* Segment labels */}
      <div className="flex gap-2 mt-2 flex-wrap">
        {segments.map((seg, i) => {
          const color = SEGMENT_COLORS[i % SEGMENT_COLORS.length]
          const isSelected = seg.segment_id === selectedSegmentId
          return (
            <button
              key={seg.segment_id}
              onClick={() => onSelectSegment(seg.segment_id)}
              className={`flex items-center gap-1.5 text-xs px-2 py-1 rounded transition-colors ${
                isSelected ? 'bg-bg-surface text-text-primary' : 'text-muted hover:text-text-primary'
              }`}
            >
              <span className={`w-2 h-2 rounded-full ${color}`} />
              {seg.segment_id}
            </button>
          )
        })}
      </div>
    </div>
  )
}
