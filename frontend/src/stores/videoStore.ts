import { create } from 'zustand'
import type { VideoProcessingStatus } from '../types/video'
import * as videosApi from '../api/videos'
import { isFullyProcessed } from '../utils/processing'

interface VideoStore {
  videos: VideoProcessingStatus[]
  uploading: Map<string, number> // filename → progress (0-100, -1 for error)
  loading: boolean
  error: string | null

  fetchVideos: (project: string) => Promise<void>
  uploadVideo: (project: string, file: File) => Promise<void>
  allProcessed: () => boolean
}

export const useVideoStore = create<VideoStore>((set, get) => ({
  videos: [],
  uploading: new Map(),
  loading: false,
  error: null,

  fetchVideos: async (project: string) => {
    set({ loading: true, error: null })
    try {
      const videos = await videosApi.listVideos(project)
      set({ videos, loading: false })
    } catch (e) {
      set({ error: String(e), loading: false })
    }
  },

  uploadVideo: async (project: string, file: File) => {
    set((s) => {
      const uploading = new Map(s.uploading)
      uploading.set(file.name, 0)
      return { uploading }
    })
    try {
      await videosApi.uploadVideo(project, file)
      set((s) => {
        const uploading = new Map(s.uploading)
        uploading.set(file.name, 100)
        return { uploading }
      })
      // Refresh video list after upload
      await get().fetchVideos(project)
      // Remove from uploading after a delay
      setTimeout(() => {
        set((s) => {
          const uploading = new Map(s.uploading)
          uploading.delete(file.name)
          return { uploading }
        })
      }, 2000)
    } catch (e) {
      set((s) => {
        const uploading = new Map(s.uploading)
        uploading.set(file.name, -1)
        return { uploading, error: String(e) }
      })
    }
  },

  allProcessed: () => {
    const { videos } = get()
    return videos.length > 0 && videos.every((v) => isFullyProcessed(v.steps))
  },
}))
