import type { TimelineOutput, TimelineSegmentEntry } from '../../types/timeline'

// Cycle through a small set of muted accent colors per scene
const SCENE_COLORS = [
  'bg-accent/40 border-accent/60',
  'bg-blue-500/30 border-blue-500/50',
  'bg-purple-500/30 border-purple-500/50',
  'bg-green-500/30 border-green-500/50',
  'bg-yellow-500/30 border-yellow-500/50',
  'bg-pink-500/30 border-pink-500/50',
]

const SCENE_COLORS_ACTIVE = [
  'bg-accent/70 border-accent',
  'bg-blue-500/60 border-blue-500',
  'bg-purple-500/60 border-purple-500',
  'bg-green-500/60 border-green-500',
  'bg-yellow-500/60 border-yellow-500',
  'bg-pink-500/60 border-pink-500',
]

interface FlatSegment {
  entry: TimelineSegmentEntry
  sceneIdx: number
  globalIdx: number
  globalStart: number  // cumulative start across all segments
}

function buildFlatSegments(timeline: TimelineOutput): FlatSegment[] {
  const flat: FlatSegment[] = []
  let globalIdx = 0
  let globalStart = 0

  for (let si = 0; si < timeline.scenes.length; si++) {
    const sorted = [...timeline.scenes[si].entries].sort((a, b) => a.position - b.position)
    for (const entry of sorted) {
      flat.push({ entry, sceneIdx: si, globalIdx: globalIdx++, globalStart })
      globalStart += entry.duration
    }
  }
  return flat
}

interface Props {
  timeline: TimelineOutput
  currentIndex: number
  currentTime: number
  onIndexChange: (idx: number) => void
}

export default function EditorTimeline({ timeline, currentIndex, currentTime, onIndexChange }: Props) {
  const flat = buildFlatSegments(timeline)
  const totalDuration = flat.reduce((sum, s) => sum + s.entry.duration, 0) || 1

  const activeSeg = flat[currentIndex]
  const globalTime = activeSeg
    ? activeSeg.globalStart + Math.max(0, currentTime - activeSeg.entry.start)
    : 0
  const playheadPct = Math.min((globalTime / totalDuration) * 100, 100)

  return (
    <div className="h-full flex flex-col">
      {/* Scene label row */}
      <div className="h-5 flex px-3 gap-px shrink-0">
        {timeline.scenes.map((scene, si) => {
          const colorClass = SCENE_COLORS[si % SCENE_COLORS.length]
          const widthPct = (scene.total_duration / totalDuration) * 100
          return (
            <div
              key={scene.scene_id}
              className={`flex items-center justify-center rounded-t text-[10px] font-mono text-white/70 border-t border-x ${colorClass}`}
              style={{ width: `${widthPct}%` }}
            >
              S{scene.scene_id}
            </div>
          )
        })}
      </div>

      {/* Segment row */}
      <div className="flex-1 px-3 overflow-hidden">
        <div className="relative flex h-full gap-0">
          {flat.map((seg) => {
            const isActive = seg.globalIdx === currentIndex
            const widthPct = (seg.entry.duration / totalDuration) * 100
            const colorClass = isActive
              ? SCENE_COLORS_ACTIVE[seg.sceneIdx % SCENE_COLORS_ACTIVE.length]
              : SCENE_COLORS[seg.sceneIdx % SCENE_COLORS.length]

            return (
              <button
                key={seg.globalIdx}
                onClick={() => onIndexChange(seg.globalIdx)}
                className={`relative border rounded-b flex items-end justify-start px-1 pb-1 group transition-colors cursor-pointer ${colorClass} ${isActive ? 'ring-1 ring-white/30' : 'hover:brightness-125'}`}
                style={{ width: `${Math.max(0.5, widthPct)}%`, minWidth: '4px' }}
                title={`Scene ${seg.entry.scene_id} · ${seg.entry.segment_id} · ${seg.entry.duration.toFixed(1)}s`}
              >
                {widthPct > 3 && (
                  <span className="text-[9px] font-mono text-white/60 truncate leading-none">
                    {seg.entry.duration.toFixed(1)}s
                  </span>
                )}
              </button>
            )
          })}

          {/* Playhead — inside the relative container so left:% matches segment widths */}
          <div
            className="absolute top-0 h-full w-0.5 bg-white/80 z-20 pointer-events-none"
            style={{ left: `${playheadPct}%` }}
          />
        </div>
      </div>

      {/* Segment info footer */}
      <div className="h-5 px-3 flex items-center shrink-0">
        {flat[currentIndex] && (
          <p className="text-[10px] text-muted font-mono truncate">
            {flat[currentIndex].entry.segment_id} &middot;{' '}
            {flat[currentIndex].entry.duration.toFixed(2)}s &middot;{' '}
            {flat[currentIndex].entry.quality_rating}
          </p>
        )}
      </div>
    </div>
  )
}
