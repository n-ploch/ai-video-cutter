import { useRef, useState } from 'react'
import type { VideoProcessingStatus } from '../../types/video'
import { getDownsampledUrl } from '../../utils/videoUrl'
import { isFullyProcessed } from '../../utils/processing'
import ProcessingIndicator from './ProcessingIndicator'

interface Props {
  video: VideoProcessingStatus
  project: string
  selected: boolean
  onClick: () => void
}

export default function VideoTile({ video, project, selected, onClick }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [hovered, setHovered] = useState(false)
  const processed = isFullyProcessed(video.steps)
  const hasDownsampled = video.steps.downsampled != null

  const displayName = video.filename.replace(/_original\.\w+$/i, '')

  return (
    <div
      onClick={onClick}
      onMouseEnter={() => {
        setHovered(true)
        if (hasDownsampled) videoRef.current?.play()
      }}
      onMouseLeave={() => {
        setHovered(false)
        if (videoRef.current) {
          videoRef.current.pause()
          videoRef.current.currentTime = 0
        }
      }}
      className={`rounded-xl overflow-hidden bg-bg-surface cursor-pointer transition-all group ${
        selected ? 'ring-2 ring-accent' : 'hover:ring-1 hover:ring-accent/50'
      }`}
    >
      {/* Video preview */}
      <div className="relative aspect-video bg-bg-primary">
        {hasDownsampled ? (
          <video
            ref={videoRef}
            src={getDownsampledUrl(project, video.video_hash, video.filename)}
            preload="metadata"
            muted
            playsInline
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="flex items-center justify-center h-full text-muted text-xs">
            Processing...
          </div>
        )}
        {hovered && hasDownsampled && (
          <div className="absolute bottom-0 left-0 right-0 h-1 bg-bg-primary/50">
            <div className="h-full bg-accent/70 transition-all" />
          </div>
        )}
      </div>

      {/* Info */}
      <div className="p-3 space-y-2">
        <p className="text-sm font-medium truncate" title={video.filename}>
          {displayName}
        </p>
        {!processed && (
          <ProcessingIndicator steps={video.steps} currentStep={video.current_step} />
        )}
      </div>
    </div>
  )
}
