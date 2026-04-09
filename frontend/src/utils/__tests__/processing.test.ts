import { describe, it, expect } from 'vitest'
import {
  computeProcessingPercent,
  getCompletedSteps,
  isFullyProcessed,
  PROCESSING_STEPS,
} from '../processing'

const ALL_NULL = Object.fromEntries(PROCESSING_STEPS.map((s) => [s, null]))
const ALL_DONE = Object.fromEntries(PROCESSING_STEPS.map((s) => [s, '2024-01-01T00:00:00Z']))

describe('computeProcessingPercent', () => {
  it('returns 0 when all steps are null', () => {
    expect(computeProcessingPercent(ALL_NULL)).toBe(0)
  })

  it('returns 100 when all steps are complete', () => {
    expect(computeProcessingPercent(ALL_DONE)).toBe(100)
  })

  it('returns 20 for one completed step', () => {
    expect(computeProcessingPercent({ ...ALL_NULL, probed: '2024-01-01T00:00:00Z' })).toBe(20)
  })

  it('returns 60 for three completed steps', () => {
    const steps = {
      ...ALL_NULL,
      probed: 'ts',
      downsampled: 'ts',
      optical_flow: 'ts',
    }
    expect(computeProcessingPercent(steps)).toBe(60)
  })
})

describe('getCompletedSteps', () => {
  it('returns empty array when nothing done', () => {
    expect(getCompletedSteps(ALL_NULL)).toEqual([])
  })

  it('returns all steps when everything done', () => {
    expect(getCompletedSteps(ALL_DONE)).toEqual([...PROCESSING_STEPS])
  })

  it('returns only completed steps in order', () => {
    const steps = { ...ALL_NULL, probed: 'ts', optical_flow: 'ts' }
    expect(getCompletedSteps(steps)).toEqual(['probed', 'optical_flow'])
  })
})

describe('isFullyProcessed', () => {
  it('returns false when all null', () => {
    expect(isFullyProcessed(ALL_NULL)).toBe(false)
  })

  it('returns true when all done', () => {
    expect(isFullyProcessed(ALL_DONE)).toBe(true)
  })

  it('returns false when last step is missing', () => {
    const steps = { ...ALL_DONE, described: null }
    expect(isFullyProcessed(steps)).toBe(false)
  })

  it('returns false when first step is missing', () => {
    const steps = { ...ALL_DONE, probed: null }
    expect(isFullyProcessed(steps)).toBe(false)
  })
})
