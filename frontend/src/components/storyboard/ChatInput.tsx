import { useState } from 'react'
import { Send } from 'lucide-react'

interface Props {
  onSubmit: (brief: string) => void
  disabled: boolean
  submitted: boolean
}

export default function ChatInput({ onSubmit, disabled, submitted }: Props) {
  const [value, setValue] = useState('')

  const handleSubmit = () => {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSubmit(trimmed)
  }

  return (
    <div className="sticky top-0 z-20 bg-bg-primary/95 backdrop-blur-sm pb-4 pt-2">
      <div className="flex gap-2 items-center">
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
          placeholder="Describe your video vision we will use to build your video..."
          disabled={submitted}
          className="flex-1 bg-bg-surface text-text-primary text-sm px-4 py-3 rounded-xl border border-border/20 outline-none focus:border-accent disabled:opacity-50 disabled:cursor-not-allowed placeholder:text-muted"
        />
        <button
          onClick={handleSubmit}
          disabled={disabled || !value.trim()}
          className="p-3 rounded-xl bg-accent text-white hover:bg-accent/80 disabled:bg-muted disabled:cursor-not-allowed transition-colors"
        >
          <Send size={18} />
        </button>
      </div>
    </div>
  )
}
