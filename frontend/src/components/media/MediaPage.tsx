import { useCallback, useEffect } from 'react'
import { useProjectStore } from '../../stores/projectStore'
import ProjectEmptyState from '../layout/ProjectEmptyState'
import { useVideoStore } from '../../stores/videoStore'
import { usePolling } from '../../hooks/usePolling'
import VideoGrid from './VideoGrid'
import VideoDetail from './VideoDetail'

export default function MediaPage() {
  const currentProject = useProjectStore((s) => s.currentProject)
  const {
    videos,
    uploading,
    error,
    selectedVideoHash,
    fetchVideos,
    uploadVideo,
    allProcessed,
    selectVideo,
  } = useVideoStore()

  useEffect(() => {
    if (currentProject) {
      fetchVideos(currentProject)
      selectVideo(null)
    }
  }, [currentProject, fetchVideos, selectVideo])

  usePolling(
    () => {
      if (currentProject) fetchVideos(currentProject)
    },
    3000,
    !currentProject || allProcessed(),
  )

  const handleUpload = useCallback(
    (files: File[]) => {
      if (!currentProject) return
      for (const file of files) {
        uploadVideo(currentProject, file)
      }
    },
    [currentProject, uploadVideo],
  )

  if (!currentProject) {
    return <ProjectEmptyState />
  }

  const selectedVideo = videos.find((v) => v.video_hash === selectedVideoHash) ?? null

  return (
    <div className="flex h-full">
      {/* Grid (shrinks when detail is open) */}
      <div
        className={`overflow-auto p-6 transition-all duration-300 ${
          selectedVideo ? 'w-1/2' : 'w-full'
        }`}
      >
        <h1 className="text-xl font-semibold mb-4">Media</h1>
        {error && (
          <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-xl text-sm text-red-400">
            {error}
          </div>
        )}
        <VideoGrid
          videos={videos}
          project={currentProject}
          selectedHash={selectedVideoHash}
          onSelect={(hash) => selectVideo(hash === selectedVideoHash ? null : hash)}
          onUpload={handleUpload}
          uploading={uploading}
        />
      </div>

      {/* Detail panel */}
      {selectedVideo && (
        <div className="w-1/2 border-l border-border/20 bg-bg-surface/30">
          <VideoDetail
            video={selectedVideo}
            project={currentProject}
            onClose={() => selectVideo(null)}
          />
        </div>
      )}
    </div>
  )
}
