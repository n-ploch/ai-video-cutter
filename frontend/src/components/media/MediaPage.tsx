import { useCallback, useEffect, useState } from 'react'
import { useProjectStore } from '../../stores/projectStore'
import { useVideoStore } from '../../stores/videoStore'
import { usePolling } from '../../hooks/usePolling'
import VideoGrid from './VideoGrid'

export default function MediaPage() {
  const currentProject = useProjectStore((s) => s.currentProject)
  const { videos, uploading, fetchVideos, uploadVideo, allProcessed } = useVideoStore()
  const [selectedHash, setSelectedHash] = useState<string | null>(null)

  // Fetch videos when project changes
  useEffect(() => {
    if (currentProject) {
      fetchVideos(currentProject)
      setSelectedHash(null)
    }
  }, [currentProject, fetchVideos])

  // Poll while any video is still processing
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
    return (
      <div className="flex items-center justify-center h-full text-muted">
        Select or create a project to get started
      </div>
    )
  }

  return (
    <div className="p-6 h-full">
      <h1 className="text-xl font-semibold mb-4">Media</h1>
      <VideoGrid
        videos={videos}
        project={currentProject}
        selectedHash={selectedHash}
        onSelect={setSelectedHash}
        onUpload={handleUpload}
        uploading={uploading}
      />
    </div>
  )
}
