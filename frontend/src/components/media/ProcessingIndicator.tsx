import { PROCESSING_STEPS, getCompletedSteps, computeProcessingPercent } from '../../utils/processing'

interface Props {
  steps: Record<string, string | null>
}

const STEP_LABELS: Record<string, string> = {
  probed: 'Probe',
  downsampled: 'Downsample',
  optical_flow: 'Optical Flow',
  segmented: 'Segmentation',
  described: 'Description',
}

export default function ProcessingIndicator({ steps }: Props) {
  const completed = getCompletedSteps(steps)
  const percent = computeProcessingPercent(steps)

  if (percent === 100) {
    return (
      <div className="flex items-center gap-1.5 text-xs text-green-400">
        <div className="w-2 h-2 rounded-full bg-green-400" />
        Ready
      </div>
    )
  }

  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2">
        <div className="flex-1 h-1.5 bg-bg-primary rounded-full overflow-hidden">
          <div
            className="h-full bg-accent rounded-full transition-all duration-500"
            style={{ width: `${percent}%` }}
          />
        </div>
        <span className="text-xs text-muted tabular-nums">{percent}%</span>
      </div>
      <div className="flex gap-1">
        {PROCESSING_STEPS.map((step) => (
          <div
            key={step}
            title={STEP_LABELS[step]}
            className={`h-1 flex-1 rounded-full transition-colors ${
              completed.includes(step) ? 'bg-accent' : 'bg-bg-primary'
            }`}
          />
        ))}
      </div>
    </div>
  )
}
