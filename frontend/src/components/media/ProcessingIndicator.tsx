import { computeProcessingPercent, STEP_LABELS } from '../../utils/processing'
import type { ProcessingStep } from '../../utils/processing'

interface Props {
  steps: Record<string, string | null>
  currentStep: string | null
}

export default function ProcessingIndicator({ steps, currentStep }: Props) {
  const percent = computeProcessingPercent(steps)

  const activeLabel =
    currentStep && currentStep in STEP_LABELS
      ? STEP_LABELS[currentStep as ProcessingStep]
      : currentStep ?? 'Processing'

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <div className="flex-1 h-1.5 bg-bg-primary rounded-full overflow-hidden">
          <div
            className="h-full bg-accent rounded-full transition-all duration-500"
            style={{ width: `${percent}%` }}
          />
        </div>
        <span className="text-xs text-muted tabular-nums">{percent}%</span>
      </div>
      <p className="text-xs text-muted">{activeLabel}…</p>
    </div>
  )
}
