import { describe, it, expect } from 'vitest'
import { getDownsampledUrl, getOriginalUrl } from '../videoUrl'

const PROJECT = 'my_project'
const HASH = '9bc3fcf2bb2d8ccf'

describe('getDownsampledUrl', () => {
  it('strips _original.MP4 suffix and appends _downsampled.mp4', () => {
    expect(getDownsampledUrl(PROJECT, HASH, 'DJI_0204_D_original.MP4')).toBe(
      `/files/${PROJECT}/videos/${HASH}/DJI_0204_D_downsampled.mp4`,
    )
  })

  it('handles lowercase .mp4 extension', () => {
    expect(getDownsampledUrl(PROJECT, HASH, 'clip_original.mp4')).toBe(
      `/files/${PROJECT}/videos/${HASH}/clip_downsampled.mp4`,
    )
  })

  it('handles .mov extension', () => {
    expect(getDownsampledUrl(PROJECT, HASH, 'shot_original.mov')).toBe(
      `/files/${PROJECT}/videos/${HASH}/shot_downsampled.mp4`,
    )
  })

  it('handles filenames without _original suffix gracefully', () => {
    // If somehow a plain filename is passed, it still appends _downsampled
    const result = getDownsampledUrl(PROJECT, HASH, 'raw.mp4')
    expect(result).toContain('_downsampled.mp4')
  })

  it('constructs correct path structure', () => {
    const url = getDownsampledUrl(PROJECT, HASH, 'DJI_0204_D_original.MP4')
    expect(url.startsWith('/files/')).toBe(true)
    expect(url).toContain(`/videos/${HASH}/`)
  })
})

describe('getOriginalUrl', () => {
  it('returns full path to original file unchanged', () => {
    expect(getOriginalUrl(PROJECT, HASH, 'DJI_0204_D_original.MP4')).toBe(
      `/files/${PROJECT}/videos/${HASH}/DJI_0204_D_original.MP4`,
    )
  })

  it('preserves uppercase extension', () => {
    const url = getOriginalUrl(PROJECT, HASH, 'clip_original.MP4')
    expect(url.endsWith('.MP4')).toBe(true)
  })
})
