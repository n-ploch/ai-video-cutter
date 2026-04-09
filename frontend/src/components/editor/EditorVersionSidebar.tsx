import { useState } from 'react'
import { ChevronLeft, ChevronRight, Plus, Loader2 } from 'lucide-react'
import type { TimelineVersionInfo } from '../../types/versions'

interface Props {
  versions: TimelineVersionInfo[]
  selectedVersion: number | null  // null = create-new / active view
  isRunning: boolean
  onCreateNew: () => void
  onSelectVersion: (v: number | null) => void  // null = return to active view
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

export default function EditorVersionSidebar({
  versions,
  selectedVersion,
  isRunning,
  onCreateNew,
  onSelectVersion,
}: Props) {
  const [collapsed, setCollapsed] = useState(false)

  const sorted = [...versions].sort((a, b) => b.version - a.version)

  if (collapsed) {
    return (
      <div className="w-10 flex flex-col items-center border-r border-border bg-bg-secondary shrink-0 py-2 gap-1">
        <button
          onClick={() => setCollapsed(false)}
          className="p-1.5 text-muted hover:text-foreground transition-colors"
          title="Expand sidebar"
        >
          <ChevronRight size={14} />
        </button>
        {isRunning ? (
          <button
            onClick={() => onSelectVersion(null)}
            className="p-1.5 text-muted hover:text-foreground transition-colors"
            title="Generating… (click to view progress)"
          >
            <Loader2 size={14} className="animate-spin" />
          </button>
        ) : (
          <button
            onClick={onCreateNew}
            className="p-1.5 text-muted hover:text-foreground transition-colors"
            title="Create New"
          >
            <Plus size={14} />
          </button>
        )}
        {sorted.map((v) => (
          <button
            key={v.version}
            onClick={() => onSelectVersion(v.version)}
            title={`v${v.version} — ${formatDate(v.created_at)}`}
            className={`text-xs font-mono px-0.5 transition-colors ${
              selectedVersion === v.version
                ? 'text-accent font-bold'
                : 'text-muted hover:text-foreground'
            }`}
          >
            {v.version}
          </button>
        ))}
      </div>
    )
  }

  return (
    <div className="w-52 flex flex-col border-r border-border bg-bg-secondary shrink-0 min-h-0">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2.5 border-b border-border">
        <span className="text-xs font-medium text-muted uppercase tracking-wider">Timeline</span>
        <button
          onClick={() => setCollapsed(true)}
          className="text-muted hover:text-foreground transition-colors"
          title="Collapse sidebar"
        >
          <ChevronLeft size={14} />
        </button>
      </div>

      {/* Create New / Generating button */}
      <div className="px-3 pt-3 pb-2">
        {isRunning ? (
          <button
            onClick={() => onSelectVersion(null)}
            className={`w-full flex items-center justify-center gap-2 py-2 px-3 rounded-lg text-sm font-medium transition-colors ${
              selectedVersion === null
                ? 'bg-muted/30 text-muted cursor-default'
                : 'bg-muted/20 text-muted hover:bg-muted/30'
            }`}
          >
            <Loader2 size={14} className="animate-spin shrink-0" />
            Generating…
          </button>
        ) : (
          <button
            onClick={onCreateNew}
            className="w-full flex items-center justify-center gap-2 py-2 px-3 bg-accent text-white rounded-lg text-sm font-medium hover:bg-accent/90 transition-colors"
          >
            <Plus size={14} />
            Create New
          </button>
        )}
      </div>

      {sorted.length > 0 && <div className="mx-3 border-t border-border mb-1" />}

      {/* Past versions list */}
      <div className="flex-1 overflow-y-auto px-2 pb-2 space-y-0.5">
        {sorted.map((v) => {
          const isSelected = selectedVersion === v.version
          return (
            <button
              key={v.version}
              onClick={() => onSelectVersion(v.version)}
              className={`w-full flex flex-col px-2 py-2 rounded-lg text-left text-xs transition-colors ${
                isSelected
                  ? 'bg-accent/15 text-accent'
                  : 'hover:bg-white/5 text-muted hover:text-foreground'
              }`}
            >
              <div className="flex items-baseline gap-2">
                <span className="font-mono font-semibold shrink-0">v{v.version}</span>
                <span className={isSelected ? 'text-accent/70' : 'text-muted'}>
                  {formatDate(v.created_at)}
                </span>
              </div>
              {v.brief_snippet && (
                <span className="mt-0.5 truncate max-w-full text-muted">{v.brief_snippet}</span>
              )}
              {v.storyboard_version != null && (
                <span className="mt-0.5 text-muted">sb v{v.storyboard_version}</span>
              )}
            </button>
          )
        })}

        {sorted.length === 0 && !isRunning && (
          <p className="text-xs text-muted px-2 py-3 text-center">No timelines yet</p>
        )}
      </div>
    </div>
  )
}
