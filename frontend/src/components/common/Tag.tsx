interface Props {
  label: string
  color?: 'default' | 'accent'
}

export default function Tag({ label, color = 'default' }: Props) {
  const base = 'inline-block px-2 py-0.5 rounded-full text-xs font-medium'
  const variant =
    color === 'accent'
      ? 'bg-accent/20 text-accent'
      : 'bg-bg-primary text-muted'
  return <span className={`${base} ${variant}`}>{label}</span>
}
