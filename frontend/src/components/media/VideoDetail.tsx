import { useEffect, useState } from 'react'
import { X } from 'lucide-react'
import type { VideoProcessingStatus } from '../../types/video'
import { useVideoStore } from '../../stores/videoStore'
import { getDownsampledUrl } from '../../utils/videoUrl'
import VideoPlayer from '../common/VideoPlayer'
import SegmentTimeline from './SegmentTimeline'
import SegmentDetail from './SegmentDetail'
import Tag from '../common/Tag'

interface Props {
  video: VideoProcessingStatus
  project: string
  onClose: () => void
}

export default function VideoDetail({ video, project, onClose }: Props) {
  const {
    vlmData,
    segments,
    segmentDescriptions,
    selectedSegmentId,
    fetchVlm,
    fetchSegments,
    fetchSegmentDescriptions,
    selectSegment,
  } = useVideoStore()

  const [currentTime, setCurrentTime] = useState(0)
  const [videoDuration, setVideoDuration] = useState(0)

  const hash = video.video_hash
  const vlm = vlmData[hash]?.vlm
  const segs = segments[hash] ?? []
  const descs = segmentDescriptions[hash] ?? []

  // Fetch data on mount
  useEffect(() => {
    fetchVlm(project, hash)
    fetchSegments(project, hash)
    fetchSegmentDescriptions(project, hash)
  }, [project, hash, fetchVlm, fetchSegments, fetchSegmentDescriptions])

  // Find selected segment and its description
  const selectedSegment = segs.find((s) => s.segment_id === selectedSegmentId) ?? null
  const selectedDesc = descs.find((d) => d.segment_id === selectedSegmentId)

  const videoSrc = getDownsampledUrl(project, hash, video.filename)

  // Constrain playback to selected segment
  const startTime = selectedSegment?.start
  const endTime = selectedSegment?.end

  const handleSeek = (time: number) => {
    // Find the video element inside VideoPlayer and seek
    const videoEl = document.querySelector<HTMLVideoElement>(`video[src="${videoSrc}"]`)
    if (videoEl) {
      videoEl.currentTime = time
    }
  }

  return (
    <div className="h-full overflow-auto p-4 space-y-4">
      {/* Close button */}
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-semibold truncate">
          {video.filename.replace(/_original\.\w+$/i, '')}
        </h2>
        <button onClick={onClose} className="text-muted hover:text-text-primary">
          <X size={20} />
        </button>
      </div>

      {/* Video player */}
      <VideoPlayer
        src={videoSrc}
        startTime={startTime}
        endTime={endTime}
        onTimeUpdate={setCurrentTime}
        onDurationChange={setVideoDuration}
      />

      {/* Segment timeline */}
      {segs.length > 0 && (
        <SegmentTimeline
          segments={segs}
          videoDuration={videoDuration}
          currentTime={currentTime}
          selectedSegmentId={selectedSegmentId}
          onSelectSegment={(id) => selectSegment(id === selectedSegmentId ? null : id)}
        />
      )}

      {/* VLM tags */}
      {vlm && (
        <div className="space-y-2">
          <div className="flex flex-wrap gap-1.5">
            {vlm.tags.map((tag) => (
              <Tag key={tag} label={tag} color="accent" />
            ))}
          </div>
          <p className="text-sm text-text-primary/70 leading-relaxed">{vlm.description}</p>
          {vlm.key_subjects.length > 0 && (
            <div className="space-y-1">
              <p className="text-xs text-muted font-medium">Key Subjects</p>
              <ul className="text-sm text-text-primary/70 space-y-0.5">
                {vlm.key_subjects.map(([name, desc], i) => (
                  <li key={i}>
                    <strong className="text-text-primary">{name}:</strong> {desc}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Selected segment detail */}
      {selectedSegment && (
        <SegmentDetail
          segment={selectedSegment}
          description={selectedDesc}
          onSeek={handleSeek}
        />
      )}
    </div>
  )
}
