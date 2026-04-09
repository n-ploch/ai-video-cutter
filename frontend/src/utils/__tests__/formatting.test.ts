import { describe, it, expect } from 'vitest'
import { formatDuration, formatTimestamp } from '../formatting'

describe('formatDuration', () => {
  it('formats zero', () => {
    expect(formatDuration(0)).toBe('0:00')
  })

  it('formats sub-minute', () => {
    expect(formatDuration(9)).toBe('0:09')
    expect(formatDuration(59)).toBe('0:59')
  })

  it('formats exactly one minute', () => {
    expect(formatDuration(60)).toBe('1:00')
  })

  it('formats minutes and seconds', () => {
    expect(formatDuration(90)).toBe('1:30')
    expect(formatDuration(125)).toBe('2:05')
  })

  it('pads single-digit seconds', () => {
    expect(formatDuration(61)).toBe('1:01')
  })

  it('formats large values', () => {
    expect(formatDuration(3600)).toBe('60:00')
  })
})

describe('formatTimestamp', () => {
  it('formats zero', () => {
    expect(formatTimestamp(0)).toBe('0:00.00')
  })

  it('formats sub-second with centiseconds', () => {
    expect(formatTimestamp(0.5)).toBe('0:00.50')
  })

  it('formats minutes, seconds, centiseconds', () => {
    expect(formatTimestamp(61.5)).toBe('1:01.50')
  })

  it('pads centiseconds to two digits', () => {
    expect(formatTimestamp(1.05)).toBe('0:01.05')
  })

  it('truncates (not rounds) centiseconds', () => {
    // 1.999 → centiseconds = floor(0.999 * 100) = 99
    expect(formatTimestamp(1.999)).toBe('0:01.99')
  })
})
