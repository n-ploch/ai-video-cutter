import { useEffect, useRef, useState } from 'react'
import { Plus, ChevronDown } from 'lucide-react'
import { useProjectStore } from '../../stores/projectStore'

export default function ProjectEmptyState() {
  const { projects, createProject, selectProject } = useProjectStore()
  const [open, setOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
        setCreating(false)
        setNewName('')
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const handleCreate = async () => {
    if (!newName.trim()) return
    try {
      await createProject(newName.trim())
      setNewName('')
      setCreating(false)
    } catch {
      // TODO: error handling
    }
  }

  return (
    <div className="flex flex-col items-center justify-center h-full">
      <div ref={ref} className="flex flex-col items-center gap-3">
        {creating ? (
          <div className="flex gap-2 items-center">
            <input
              autoFocus
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleCreate()
                if (e.key === 'Escape') {
                  setCreating(false)
                  setNewName('')
                }
              }}
              placeholder="project_name"
              className="bg-bg-primary text-text-primary text-sm px-3 py-1.5 rounded-lg border border-border/30 outline-none focus:border-accent w-44"
            />
            <button
              onClick={handleCreate}
              className="px-3 py-1.5 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent/80 transition-colors"
            >
              Create
            </button>
          </div>
        ) : (
          <button
            onClick={() => setCreating(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg border border-accent/30 bg-accent/10 text-accent text-sm font-medium hover:bg-accent/20 transition-colors"
          >
            <Plus size={14} />
            Create new project
          </button>
        )}

        <div className="relative">
          <button
            onClick={() => setOpen(!open)}
            className="flex items-center gap-1 w-56 px-2 py-1.5 rounded text-xs text-text-primary hover:bg-bg-primary/50 transition-colors bg-bg-surface border border-border/30"
          >
            <span className="flex-1 text-left truncate">Select project</span>
            <ChevronDown size={12} className="shrink-0" />
          </button>

          {open && (
            <div className="absolute left-0 top-full mt-1 w-56 bg-bg-surface border border-border/30 rounded-lg shadow-lg z-50 py-1">
              {projects.length === 0 ? (
                <div className="px-3 py-2 text-sm text-muted">No projects yet</div>
              ) : (
                projects.map((p) => (
                  <button
                    key={p.name}
                    onClick={() => {
                      selectProject(p.name)
                      setOpen(false)
                    }}
                    className="w-full text-left px-3 py-2 text-sm text-text-primary hover:bg-bg-primary/50 transition-colors"
                  >
                    {p.name}
                  </button>
                ))
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
