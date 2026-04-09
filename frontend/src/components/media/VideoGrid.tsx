import type { VideoProcessingStatus } from '../../types/video'
import VideoTile from './VideoTile'
import UploadZone from './UploadZone'

interface Props {
  videos: VideoProcessingStatus[]
  project: string
  selectedHash: string | null
  onSelect: (hash: string) => void
  onUpload: (files: File[]) => void
  uploading: Map<string, number>
}

export default function VideoGrid({
  videos,
  project,
  selectedHash,
  onSelect,
  onUpload,
  uploading,
}: Props) {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
      <UploadZone onFiles={onUpload} uploading={uploading} />
      {videos.map((v) => (
        <VideoTile
          key={v.video_hash}
          video={v}
          project={project}
          selected={selectedHash === v.video_hash}
          onClick={() => onSelect(v.video_hash)}
        />
      ))}
    </div>
  )
}
