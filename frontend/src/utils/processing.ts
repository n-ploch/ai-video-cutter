const PROCESSING_STEPS = ['downsampled', 'optical_flow', 'segmented', 'described'] as const

export type ProcessingStep = typeof PROCESSING_STEPS[number]

export const STEP_LABELS: Record<ProcessingStep, string> = {
  downsampled: 'Downsampling',
  optical_flow: 'Indexing',
  segmented: 'Segmenting',
  described: 'Describing',
}

export function computeProcessingPercent(steps: Record<string, string | null>): number {
  const completed = PROCESSING_STEPS.filter((s) => steps[s] != null).length
  return Math.round((completed / PROCESSING_STEPS.length) * 100)
}

export function getCompletedSteps(steps: Record<string, string | null>): ProcessingStep[] {
  return PROCESSING_STEPS.filter((s) => steps[s] != null) as ProcessingStep[]
}

export function isFullyProcessed(steps: Record<string, string | null>): boolean {
  return PROCESSING_STEPS.every((s) => steps[s] != null)
}

export { PROCESSING_STEPS }
