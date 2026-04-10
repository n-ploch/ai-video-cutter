import { useEffect, useRef, useState } from 'react'
import { Plus, ChevronDown } from 'lucide-react'
import { useProjectStore } from '../../stores/projectStore'

export default function ProjectSelector() {
  const { projects, currentProject, fetchProjects, createProject, selectProject } =
    useProjectStore()
  const [open, setOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetchProjects()
  }, [fetchProjects])

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
      setOpen(false)
    } catch {
      // TODO: error handling in Phase 7
    }
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1 w-full px-2 py-1.5 rounded text-xs text-text-primary hover:bg-bg-primary/50 transition-colors truncate"
      >
        <span className="truncate opacity-0 group-hover/sidebar:opacity-100 transition-opacity">
          {currentProject || 'Select project'}
        </span>
        <ChevronDown size={12} className="shrink-0 opacity-0 group-hover/sidebar:opacity-100" />
      </button>

      {open && (
        <div className="absolute left-0 top-full mt-1 w-56 bg-bg-surface border border-border/30 rounded-lg shadow-lg z-50 py-1">
          {projects.map((p) => (
            <button
              key={p.name}
              onClick={() => {
                selectProject(p.name)
                setOpen(false)
              }}
              className={`w-full text-left px-3 py-2 text-sm hover:bg-bg-primary/50 transition-colors ${
                currentProject === p.name ? 'text-accent' : 'text-text-primary'
              }`}
            >
              {p.name}
            </button>
          ))}

          {creating ? (
            <div className="px-3 py-2 flex gap-2">
              <input
                autoFocus
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
                placeholder="project_name"
                className="flex-1 bg-bg-primary text-text-primary text-sm px-2 py-1 rounded border border-border/30 outline-none focus:border-accent"
              />
              <button
                onClick={handleCreate}
                className="text-accent hover:text-accent/80 text-sm font-medium"
              >
                Add
              </button>
            </div>
          ) : (
            <button
              onClick={() => setCreating(true)}
              className="w-full text-left px-3 py-2 text-sm text-accent hover:bg-bg-primary/50 flex items-center gap-2"
            >
              <Plus size={14} />
              New Project
            </button>
          )}
        </div>
      )}
    </div>
  )
}
