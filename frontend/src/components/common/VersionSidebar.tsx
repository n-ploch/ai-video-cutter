import { useState } from 'react'
import { ChevronLeft, ChevronRight, Plus, Loader2 } from 'lucide-react'

interface VersionEntry {
  version: number
  created_at: string
  brief_snippet?: string | null
}

interface VersionSidebarProps<T extends VersionEntry> {
  label: string
  versions: T[]
  selectedVersion: number | null  // null = active/latest
  isActiveRunning: boolean
  onSelectVersion: (v: number | null) => void
  onNew: () => void
  renderMeta?: (v: T) => React.ReactNode
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

export default function VersionSidebar<T extends VersionEntry>({
  label,
  versions,
  selectedVersion,
  isActiveRunning,
  onSelectVersion,
  onNew,
  renderMeta,
}: VersionSidebarProps<T>) {
  const [collapsed, setCollapsed] = useState(false)

  const showSpinnerEntry = isActiveRunning

  // Versions displayed newest first
  const sorted = [...versions].sort((a, b) => b.version - a.version)

  if (collapsed) {
    return (
      <div className="w-10 flex flex-col border-r border-border bg-bg-secondary shrink-0">
        <button
          onClick={() => setCollapsed(false)}
          className="p-2 hover:text-foreground text-muted transition-colors mt-2 mx-auto"
          title={`Expand ${label} versions`}
        >
          <ChevronRight size={16} />
        </button>
        {showSpinnerEntry && (
          <div className="flex justify-center mt-2">
            <Loader2 size={14} className="animate-spin text-accent" />
          </div>
        )}
        {sorted.slice(0, 5).map((v) => (
          <button
            key={v.version}
            onClick={() => onSelectVersion(v.version)}
            className={`mx-auto mt-1 text-xs font-mono px-1 rounded transition-colors ${
              selectedVersion === v.version
                ? 'text-accent font-bold'
                : 'text-muted hover:text-foreground'
            }`}
            title={`v${v.version} — ${formatDate(v.created_at)}`}
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
      <div className="flex items-center justify-between px-3 py-2 border-b border-border">
        <span className="text-xs font-medium text-muted uppercase tracking-wider">{label}</span>
        <button
          onClick={() => setCollapsed(true)}
          className="text-muted hover:text-foreground transition-colors"
          title="Collapse sidebar"
        >
          <ChevronLeft size={14} />
        </button>
      </div>

      {/* New button */}
      <button
        onClick={onNew}
        className="flex items-center gap-2 mx-3 mt-2 mb-1 px-2 py-1.5 text-xs text-muted hover:text-foreground hover:bg-white/5 rounded-lg transition-colors"
      >
        <Plus size={13} />
        New
      </button>

      {/* Version list */}
      <div className="flex-1 overflow-y-auto px-2 pb-2 space-y-0.5">
        {/* Active/in-progress entry */}
        {showSpinnerEntry && (
          <button
            onClick={() => onSelectVersion(null)}
            className={`w-full flex items-center gap-2 px-2 py-2 rounded-lg text-left text-xs transition-colors ${
              selectedVersion === null
                ? 'bg-accent/15 text-accent'
                : 'hover:bg-white/5 text-muted'
            }`}
          >
            <Loader2 size={12} className="animate-spin shrink-0" />
            <span className="truncate">Generating…</span>
          </button>
        )}

        {/* Latest (non-running) active entry when no version selected */}
        {!showSpinnerEntry && versions.length > 0 && selectedVersion === null && (
          <button
            onClick={() => onSelectVersion(null)}
            className="w-full flex items-center gap-2 px-2 py-2 rounded-lg text-left text-xs bg-accent/15 text-accent"
          >
            <span className="font-mono font-bold shrink-0">
              v{sorted[0]?.version}
            </span>
            <span className="truncate text-accent/70">latest</span>
          </button>
        )}

        {/* Historical versions */}
        {sorted.map((v) => {
          // When not running: skip rendering v[latest] as a separate entry if it's already
          // shown as the "active" entry above. Show all when a specific version is selected.
          const isLatest = v.version === sorted[0]?.version
          if (!showSpinnerEntry && isLatest && selectedVersion === null) return null

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
                <span className={`${isSelected ? 'text-accent/70' : 'text-muted'}`}>
                  {formatDate(v.created_at)}
                </span>
              </div>
              {renderMeta?.(v)}
            </button>
          )
        })}

        {versions.length === 0 && !isActiveRunning && (
          <p className="text-xs text-muted px-2 py-4 text-center">No versions yet</p>
        )}
      </div>
    </div>
  )
}
