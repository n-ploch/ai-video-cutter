import { useNavigate } from 'react-router'
import { Loader2 } from 'lucide-react'

interface Props {
  isRunning: boolean
  hasStoryboard: boolean
}

export default function UseStoryboardButton({ isRunning, hasStoryboard }: Props) {
  const navigate = useNavigate()

  if (isRunning) {
    return (
      <div className="flex items-center justify-center gap-3 py-4 px-6 bg-muted/20 rounded-xl text-muted">
        <Loader2 size={20} className="animate-spin" />
        Building storyboard...
      </div>
    )
  }

  if (!hasStoryboard) return null

  return (
    <button
      onClick={() => navigate('/editor')}
      className="w-full py-4 px-6 bg-accent text-white text-lg font-semibold rounded-xl hover:bg-accent/90 transition-colors"
    >
      Use Storyboard
    </button>
  )
}
