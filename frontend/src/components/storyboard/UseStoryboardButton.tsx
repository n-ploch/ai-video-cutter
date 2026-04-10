import { useNavigate } from 'react-router'
import { Loader2 } from 'lucide-react'
import { useEditorStore } from '../../stores/editorStore'

interface Props {
  isRunning: boolean
  hasStoryboard: boolean
  viewedVersion: number | null  // null = latest/active
}

export default function UseStoryboardButton({ isRunning, hasStoryboard, viewedVersion }: Props) {
  const navigate = useNavigate()
  const setSelectedStoryboardVersion = useEditorStore((s) => s.setSelectedStoryboardVersion)

  if (isRunning) {
    return (
      <div className="flex items-center justify-center gap-3 py-4 px-6 bg-muted/20 rounded-xl text-muted">
        <Loader2 size={20} className="animate-spin" />
        Building storyboard...
      </div>
    )
  }

  if (!hasStoryboard) return null

  const handleClick = () => {
    // Pass the viewed version to editor so the dropdown pre-selects it
    setSelectedStoryboardVersion(viewedVersion)
    navigate('/editor')
  }

  return (
    <button
      onClick={handleClick}
      className="w-full py-4 px-6 bg-accent text-white text-lg font-semibold rounded-xl hover:bg-accent/90 transition-colors"
    >
      Use Storyboard{viewedVersion !== null ? ` (v${viewedVersion})` : ''}
    </button>
  )
}
