const PROCESSING_STEPS = ['probed', 'downsampled', 'optical_flow', 'segmented', 'described'] as const

export type ProcessingStep = typeof PROCESSING_STEPS[number]

export function computeProcessingPercent(steps: Record<string, string | null>): number {
  const completed = PROCESSING_STEPS.filter((s) => steps[s] != null).length
  return Math.round((completed / PROCESSING_STEPS.length) * 100)
}

export function getCompletedSteps(steps: Record<string, string | null>): ProcessingStep[] {
  return PROCESSING_STEPS.filter((s) => steps[s] != null)
}

export function isFullyProcessed(steps: Record<string, string | null>): boolean {
  return PROCESSING_STEPS.every((s) => steps[s] != null)
}

export { PROCESSING_STEPS }
