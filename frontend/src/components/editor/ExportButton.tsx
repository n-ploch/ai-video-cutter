import { useState } from 'react'
import { Download, Loader2 } from 'lucide-react'
import { triggerExport } from '../../api/export'

interface Props {
  projectName: string
}

export default function ExportButton({ projectName }: Props) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleExport = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await triggerExport(projectName)
      // Trigger browser download
      const a = document.createElement('a')
      a.href = res.otio_url
      a.download = `${projectName}_v${res.version}.otio`
      a.click()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-1">
      <button
        onClick={handleExport}
        disabled={loading}
        className="flex items-center gap-2 px-4 py-2 bg-bg-secondary border border-border rounded-xl text-sm font-medium hover:border-accent/60 hover:text-accent transition-colors disabled:opacity-50"
      >
        {loading ? (
          <Loader2 size={14} className="animate-spin" />
        ) : (
          <Download size={14} />
        )}
        {loading ? 'Exporting…' : 'Export OTIO'}
      </button>
      {error && (
        <p className="text-xs text-red-400">{error}</p>
      )}
    </div>
  )
}
