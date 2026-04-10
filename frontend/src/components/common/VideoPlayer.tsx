import { useRef, useEffect, useCallback, useState } from 'react'
import { Play, Pause } from 'lucide-react'
import { formatTimestamp } from '../../utils/formatting'

interface Props {
  src: string
  startTime?: number
  endTime?: number
  onTimeUpdate?: (time: number) => void
  onDurationChange?: (duration: number) => void
  className?: string
}

export default function VideoPlayer({ src, startTime, endTime, onTimeUpdate, onDurationChange, className = '' }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [playing, setPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)

  // Seek to startTime when constraints change
  useEffect(() => {
    const v = videoRef.current
    if (!v) return
    if (startTime != null && v.currentTime < startTime) {
      v.currentTime = startTime
    }
  }, [startTime, src])

  const handleTimeUpdate = useCallback(() => {
    const v = videoRef.current
    if (!v) return
    const t = v.currentTime

    // Enforce bounds
    if (startTime != null && t < startTime) {
      v.currentTime = startTime
      return
    }
    if (endTime != null && t >= endTime) {
      v.pause()
      v.currentTime = endTime - 0.01
      setPlaying(false)
      return
    }

    setCurrentTime(t)
    onTimeUpdate?.(t)
  }, [startTime, endTime, onTimeUpdate])

  const togglePlay = useCallback(() => {
    const v = videoRef.current
    if (!v) return
    if (v.paused) {
      // If at end of constrained region, restart
      if (endTime != null && v.currentTime >= endTime - 0.1) {
        v.currentTime = startTime ?? 0
      }
      v.play()
      setPlaying(true)
    } else {
      v.pause()
      setPlaying(false)
    }
  }, [startTime, endTime])

  const handleScrub = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      const v = videoRef.current
      if (!v) return
      const rect = e.currentTarget.getBoundingClientRect()
      const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
      const lo = startTime ?? 0
      const hi = endTime ?? duration
      v.currentTime = lo + ratio * (hi - lo)
    },
    [startTime, endTime, duration],
  )

  const lo = startTime ?? 0
  const hi = endTime ?? duration
  const range = hi - lo || 1
  const progress = ((currentTime - lo) / range) * 100

  return (
    <div className={`flex flex-col ${className}`}>
      <div className="relative bg-black rounded-lg overflow-hidden cursor-pointer" onClick={togglePlay}>
        <video
          ref={videoRef}
          src={src}
          preload="auto"
          onTimeUpdate={handleTimeUpdate}
          onLoadedMetadata={() => {
            const v = videoRef.current
            if (v) {
              setDuration(v.duration)
              onDurationChange?.(v.duration)
              if (startTime != null) v.currentTime = startTime
            }
          }}
          onEnded={() => setPlaying(false)}
          className="w-full"
        />
        {!playing && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/20">
            <Play size={40} className="text-white/80" />
          </div>
        )}
      </div>

      {/* Controls */}
      <div className="flex items-center gap-3 mt-2 px-1">
        <button onClick={togglePlay} className="text-text-primary hover:text-accent transition-colors">
          {playing ? <Pause size={16} /> : <Play size={16} />}
        </button>

        {/* Scrubber */}
        <div
          className="flex-1 h-1.5 bg-bg-primary rounded-full cursor-pointer relative group"
          onClick={handleScrub}
        >
          <div
            className="absolute h-full bg-accent rounded-full transition-[width] duration-75"
            style={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
          />
          <div
            className="absolute top-1/2 -translate-y-1/2 w-3 h-3 bg-accent rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
            style={{ left: `calc(${Math.min(100, Math.max(0, progress))}% - 6px)` }}
          />
        </div>

        <span className="text-xs text-muted tabular-nums whitespace-nowrap">
          {formatTimestamp(currentTime)} / {formatTimestamp(hi)}
        </span>
      </div>
    </div>
  )
}
