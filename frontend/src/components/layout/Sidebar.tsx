import { NavLink } from 'react-router'
import { Film, BookOpen, Scissors } from 'lucide-react'
import ProjectSelector from './ProjectSelector'

const navItems = [
  { to: '/media', label: 'Media', icon: Film },
  { to: '/storyboard', label: 'Storyboard', icon: BookOpen },
  { to: '/editor', label: 'Editor', icon: Scissors },
]

export default function Sidebar() {
  return (
    <aside className="flex flex-col w-16 hover:w-48 group/sidebar bg-bg-surface border-r border-border/20 transition-all duration-200 overflow-hidden shrink-0">
      <div className="p-2 border-b border-border/20">
        <ProjectSelector />
      </div>
      <nav className="flex flex-col gap-1 p-2 mt-2">
        {navItems.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${
                isActive
                  ? 'bg-accent text-white'
                  : 'text-muted hover:text-text-primary hover:bg-bg-primary/50'
              }`
            }
          >
            <Icon size={20} className="shrink-0" />
            <span className="opacity-0 group-hover/sidebar:opacity-100 transition-opacity whitespace-nowrap">
              {label}
            </span>
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}
