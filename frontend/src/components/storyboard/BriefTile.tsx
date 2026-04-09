interface Props {
  brief: string
}

export default function BriefTile({ brief }: Props) {
  return (
    <div className="p-4 bg-bg-surface rounded-xl">
      <p className="text-xs text-muted font-medium mb-1">Brief</p>
      <p className="text-sm text-text-primary">{brief}</p>
    </div>
  )
}
