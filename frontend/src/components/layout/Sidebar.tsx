import { NavLink } from 'react-router'
import { Film, BookOpen, Scissors, HelpCircle } from 'lucide-react'
import ProjectSelector from './ProjectSelector'

const navItems = [
  { to: '/media', label: 'Media', icon: Film },
  { to: '/storyboard', label: 'Storyboard', icon: BookOpen },
  { to: '/editor', label: 'Editor', icon: Scissors },
]

function NavItem({ to, label, icon: Icon }: { to: string; label: string; icon: React.ElementType }) {
  return (
    <NavLink
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
  )
}

export default function Sidebar() {
  return (
    <aside className="flex flex-col w-16 hover:w-48 group/sidebar bg-bg-surface border-r border-border/20 transition-all duration-200 overflow-hidden shrink-0">
      <div className="p-2 border-b border-border/20">
        <ProjectSelector />
      </div>
      <nav className="flex flex-col gap-1 p-2 mt-2 flex-1">
        {navItems.map((item) => (
          <NavItem key={item.to} {...item} />
        ))}
      </nav>
      <div className="p-2 border-t border-border/20">
        <NavItem to="/help" label="Help" icon={HelpCircle} />
      </div>
    </aside>
  )
}
