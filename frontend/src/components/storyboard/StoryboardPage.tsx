import { useProjectStore } from '../../stores/projectStore'

export default function StoryboardPage() {
  const currentProject = useProjectStore((s) => s.currentProject)

  if (!currentProject) {
    return (
      <div className="flex items-center justify-center h-full text-muted">
        Select or create a project to get started
      </div>
    )
  }

  return (
    <div className="p-6">
      <h1 className="text-xl font-semibold mb-4">Storyboard</h1>
      <p className="text-muted text-sm">Create your video storyboard with AI.</p>
    </div>
  )
}
