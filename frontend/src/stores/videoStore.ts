import { create } from 'zustand'
import type { VideoProcessingStatus, VideoDescription } from '../types/video'
import type { SegmentBase, SegmentDescription } from '../types/segment'
import * as videosApi from '../api/videos'
import { isFullyProcessed } from '../utils/processing'

interface VideoStore {
  videos: VideoProcessingStatus[]
  uploading: Map<string, number>
  loading: boolean
  error: string | null

  // Detail / selection state
  selectedVideoHash: string | null
  selectedSegmentId: string | null
  vlmData: Record<string, VideoDescription>
  segments: Record<string, SegmentBase[]>
  segmentDescriptions: Record<string, SegmentDescription[]>

  fetchVideos: (project: string) => Promise<void>
  uploadVideo: (project: string, file: File) => Promise<void>
  allProcessed: () => boolean

  selectVideo: (hash: string | null) => void
  selectSegment: (segmentId: string | null) => void
  fetchVlm: (project: string, hash: string) => Promise<void>
  fetchSegments: (project: string, hash: string) => Promise<void>
  fetchSegmentDescriptions: (project: string, hash: string) => Promise<void>
}

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`Failed to fetch ${url}: ${res.status}`)
  return res.json()
}

export const useVideoStore = create<VideoStore>((set, get) => ({
  videos: [],
  uploading: new Map(),
  loading: false,
  error: null,
  selectedVideoHash: null,
  selectedSegmentId: null,
  vlmData: {},
  segments: {},
  segmentDescriptions: {},

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
      await get().fetchVideos(project)
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

  selectVideo: (hash) => set({ selectedVideoHash: hash, selectedSegmentId: null }),
  selectSegment: (segmentId) => set({ selectedSegmentId: segmentId }),

  fetchVlm: async (project, hash) => {
    if (get().vlmData[hash]) return
    try {
      const data = await fetchJson<VideoDescription>(
        `/files/${project}/videos/${hash}/descriptions/vlm.json`,
      )
      set((s) => ({ vlmData: { ...s.vlmData, [hash]: data } }))
    } catch {
      // VLM not yet available — ignore
    }
  },

  fetchSegments: async (project, hash) => {
    if (get().segments[hash]) return
    try {
      const data = await fetchJson<SegmentBase[]>(
        `/files/${project}/videos/${hash}/segments/segments.json`,
      )
      set((s) => ({ segments: { ...s.segments, [hash]: data } }))
    } catch {
      // Segments not yet available
    }
  },

  fetchSegmentDescriptions: async (project, hash) => {
    if (get().segmentDescriptions[hash]) return
    try {
      const data = await fetchJson<SegmentDescription[]>(
        `/files/${project}/videos/${hash}/segments/descriptions.json`,
      )
      set((s) => ({ segmentDescriptions: { ...s.segmentDescriptions, [hash]: data } }))
    } catch {
      // Descriptions not yet available
    }
  },
}))
