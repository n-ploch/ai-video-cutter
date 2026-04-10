import { useRef, useEffect, useCallback, useState } from 'react'
import { Play, Pause, SkipBack, SkipForward } from 'lucide-react'
import type { TimelineOutput, TimelineSegmentEntry } from '../../types/timeline'
import { getDownsampledUrl } from '../../utils/videoUrl'
import { formatTimestamp } from '../../utils/formatting'

interface FlatEntry extends TimelineSegmentEntry {
  sceneIndex: number
  globalIndex: number
}

function flattenTimeline(timeline: TimelineOutput): FlatEntry[] {
  const entries: FlatEntry[] = []
  let globalIndex = 0
  for (let si = 0; si < timeline.scenes.length; si++) {
    const scene = timeline.scenes[si]
    // sort by position within scene
    const sorted = [...scene.entries].sort((a, b) => a.position - b.position)
    for (const entry of sorted) {
      entries.push({ ...entry, sceneIndex: si, globalIndex: globalIndex++ })
    }
  }
  return entries
}

interface Props {
  project: string
  timeline: TimelineOutput
  currentIndex: number
  onIndexChange: (idx: number) => void
  onTimeUpdate?: (t: number) => void
}

export default function EditorPreview({ project, timeline, currentIndex, onIndexChange, onTimeUpdate }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [playing, setPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)

  const prevSrcRef    = useRef<string>('')
  const playingRef    = useRef(false)
  const entryStartRef = useRef(0)

  const entries = flattenTimeline(timeline)
  const entry = entries[currentIndex]
  const nextEntry = entries[currentIndex + 1]

  const src = entry
    ? getDownsampledUrl(project, entry.source_video, entry.video_file)
    : ''
  // Preload next segment's source file in the background so switching is seamless
  const nextSrc = nextEntry
    ? getDownsampledUrl(project, nextEntry.source_video, nextEntry.video_file)
    : null

  // Keep refs in sync with current render values so async callbacks see fresh data
  playingRef.current    = playing
  entryStartRef.current = entry?.start ?? 0

  // Seek to segment start when entry changes
  useEffect(() => {
    const v = videoRef.current
    if (!v || !entry) return

    if (src === prevSrcRef.current) {
      // Same source file — browser already has it, safe to seek immediately
      v.currentTime = entry.start
      setCurrentTime(entry.start)
      onTimeUpdate?.(entry.start)
      if (playing) v.play().catch(() => {})
    } else {
      // Source file changed — browser will reload; onLoadedMetadata will finish the job
      prevSrcRef.current = src
      entryStartRef.current = entry.start
      setCurrentTime(entry.start)
      onTimeUpdate?.(entry.start)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentIndex, src])

  const handleTimeUpdate = useCallback(() => {
    const v = videoRef.current
    if (!v || !entry) return
    const t = v.currentTime

    if (t < entry.start) {
      v.currentTime = entry.start
      return
    }
    if (t >= entry.end) {
      // Advance to next segment
      if (currentIndex < entries.length - 1) {
        onIndexChange(currentIndex + 1)
      } else {
        v.pause()
        setPlaying(false)
      }
      return
    }
    setCurrentTime(t)
    onTimeUpdate?.(t)
  }, [entry, currentIndex, entries.length, onIndexChange, onTimeUpdate])

  const togglePlay = useCallback(() => {
    const v = videoRef.current
    if (!v || !entry) return
    if (v.paused) {
      if (v.currentTime >= entry.end - 0.05) {
        v.currentTime = entry.start
      }
      v.play().catch(() => {})
      setPlaying(true)
    } else {
      v.pause()
      setPlaying(false)
    }
  }, [entry])

  const handleScrub = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      const v = videoRef.current
      if (!v || !entry) return
      const rect = e.currentTarget.getBoundingClientRect()
      const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
      v.currentTime = entry.start + ratio * (entry.end - entry.start)
    },
    [entry],
  )

  const segDuration = entry ? entry.end - entry.start : 1
  const progress = entry ? Math.max(0, Math.min(1, (currentTime - entry.start) / segDuration)) * 100 : 0

  if (!entry) return null

  return (
    <div className="flex flex-col h-full">
      {/* Video */}
      <div
        className="relative bg-black rounded-xl overflow-hidden flex-1 cursor-pointer"
        onClick={togglePlay}
      >
        <video
          ref={videoRef}
          src={src}
          preload="auto"
          onTimeUpdate={handleTimeUpdate}
          onLoadedMetadata={() => {
            const v = videoRef.current
            if (!v) return
            v.currentTime = entryStartRef.current
            if (playingRef.current) v.play().catch(() => {})
          }}
          onEnded={() => {}}
          className="w-full h-full object-contain"
        />
        {/* Preload next segment's source file while current one plays */}
        {nextSrc && nextSrc !== src && (
          <video key={nextSrc} src={nextSrc} preload="auto" className="hidden" aria-hidden />
        )}

        {!playing && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/20">
            <Play size={48} className="text-white/80" />
          </div>
        )}

        {/* Scene / segment badge */}
        <div className="absolute top-3 left-3 flex gap-2">
          <span className="bg-black/60 text-white text-xs px-2 py-1 rounded font-mono">
            Scene {entry.scene_id}
          </span>
          <span className="bg-black/60 text-muted text-xs px-2 py-1 rounded font-mono">
            {currentIndex + 1}/{entries.length}
          </span>
        </div>
      </div>

      {/* Controls */}
      <div className="mt-2 space-y-2 px-1">
        {/* Scrubber */}
        <div
          className="h-1.5 bg-bg-primary rounded-full cursor-pointer relative group"
          onClick={handleScrub}
        >
          <div
            className="absolute h-full bg-accent rounded-full"
            style={{ width: `${progress}%` }}
          />
          <div
            className="absolute top-1/2 -translate-y-1/2 w-3 h-3 bg-accent rounded-full opacity-0 group-hover:opacity-100"
            style={{ left: `calc(${progress}% - 6px)` }}
          />
        </div>

        {/* Buttons + time */}
        <div className="flex items-center gap-3">
          <button
            onClick={() => onIndexChange(Math.max(0, currentIndex - 1))}
            disabled={currentIndex === 0}
            className="text-muted hover:text-foreground disabled:opacity-30 transition-colors"
          >
            <SkipBack size={16} />
          </button>
          <button onClick={togglePlay} className="text-foreground hover:text-accent transition-colors">
            {playing ? <Pause size={16} /> : <Play size={16} />}
          </button>
          <button
            onClick={() => onIndexChange(Math.min(entries.length - 1, currentIndex + 1))}
            disabled={currentIndex === entries.length - 1}
            className="text-muted hover:text-foreground disabled:opacity-30 transition-colors"
          >
            <SkipForward size={16} />
          </button>

          <span className="text-xs text-muted tabular-nums ml-auto">
            {formatTimestamp(currentTime - entry.start)} / {formatTimestamp(segDuration)}
          </span>
        </div>
      </div>
    </div>
  )
}
