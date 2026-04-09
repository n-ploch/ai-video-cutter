import { useCallback, useRef, useState } from 'react'
import { Upload } from 'lucide-react'

interface Props {
  onFiles: (files: File[]) => void
  uploading: Map<string, number>
}

const ACCEPTED = '.mp4,.mov'

export default function UploadZone({ onFiles, uploading }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)

  const handleFiles = useCallback(
    (fileList: FileList | null) => {
      if (!fileList) return
      const valid = Array.from(fileList).filter((f) =>
        /\.(mp4|mov)$/i.test(f.name),
      )
      if (valid.length) onFiles(valid)
    },
    [onFiles],
  )

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault()
        setDragOver(true)
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragOver(false)
        handleFiles(e.dataTransfer.files)
      }}
      onClick={() => inputRef.current?.click()}
      className={`flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed cursor-pointer transition-colors min-h-[200px] ${
        dragOver
          ? 'border-accent bg-accent/10'
          : 'border-border/30 hover:border-accent/50 bg-bg-surface/50'
      }`}
    >
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED}
        multiple
        className="hidden"
        onChange={(e) => handleFiles(e.target.files)}
      />
      <Upload size={32} className="text-muted" />
      <span className="text-sm text-muted">
        Drop .mp4 / .mov files or click to upload
      </span>
      {uploading.size > 0 && (
        <div className="text-xs text-accent mt-1">
          Uploading {uploading.size} file{uploading.size > 1 ? 's' : ''}...
        </div>
      )}
    </div>
  )
}
