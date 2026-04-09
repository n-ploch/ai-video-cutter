import { Loader2 } from 'lucide-react'
import {
  useEditorStore,
  PHASE_LABELS,
  phaseIndex,
  type EditorPhase,
} from '../../stores/editorStore'

const ACTIVE_PHASES: EditorPhase[] = [
  'fetching_candidates',
  'assembling_scenes',
  'stitching',
  'reviewing',
  'persisting',
]

interface Props {
  projectName: string
}

export default function StartEditingButton({ projectName }: Props) {
  const { isRunning, phase, error, triggerEditor } = useEditorStore()

  if (error) {
    return (
      <div className="space-y-2">
        <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-xl text-sm text-red-400">
          {error}
        </div>
        <button
          onClick={() => triggerEditor(projectName)}
          className="w-full py-3 px-6 bg-accent text-white font-semibold rounded-xl hover:bg-accent/90 transition-colors"
        >
          Retry
        </button>
      </div>
    )
  }

  if (phase === 'done') {
    return (
      <div className="py-3 px-6 bg-green-500/20 border border-green-500/30 rounded-xl text-center text-green-400 font-semibold">
        Timeline ready
      </div>
    )
  }

  if (isRunning) {
    const currentIdx = phaseIndex(phase)
    return (
      <div className="space-y-3 p-4 bg-bg-secondary rounded-xl border border-border">
        <div className="flex items-center gap-2 text-sm text-foreground">
          <Loader2 size={16} className="animate-spin text-accent" />
          <span>{PHASE_LABELS[phase]}</span>
        </div>
        <div className="flex gap-1">
          {ACTIVE_PHASES.map((p, i) => (
            <div
              key={p}
              className={`flex-1 h-1.5 rounded-full transition-colors ${
                i < currentIdx
                  ? 'bg-accent'
                  : i === currentIdx
                    ? 'bg-accent/60'
                    : 'bg-border'
              }`}
            />
          ))}
        </div>
        <div className="flex justify-between text-xs text-muted">
          {ACTIVE_PHASES.map((p) => (
            <span
              key={p}
              className={phaseIndex(p) <= currentIdx ? 'text-accent' : ''}
            >
              {p === 'fetching_candidates'
                ? 'Fetch'
                : p === 'assembling_scenes'
                  ? 'Assemble'
                  : p === 'stitching'
                    ? 'Stitch'
                    : p === 'reviewing'
                      ? 'Review'
                      : 'Save'}
            </span>
          ))}
        </div>
      </div>
    )
  }

  return (
    <button
      onClick={() => triggerEditor(projectName)}
      className="w-full py-3 px-6 bg-accent text-white font-semibold rounded-xl hover:bg-accent/90 transition-colors"
    >
      Start Editing
    </button>
  )
}
