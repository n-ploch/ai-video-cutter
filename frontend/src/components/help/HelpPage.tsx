import { Film, BookOpen, Scissors, FolderOpen, Upload, Sparkles, Clapperboard } from 'lucide-react'

const tabs = [
  {
    icon: Film,
    label: 'Media',
    description:
      'Upload your raw footage here. Each video is automatically analysed by a vision model that transcribes dialogue, detects camera movements, and segments the clip into labelled shots. Processing runs in the background — you can leave the page and come back.',
  },
  {
    icon: BookOpen,
    label: 'Storyboard',
    description:
      'Describe what you want your video to say or show, and the AI generates a scene-by-scene storyboard. Each version is saved so you can compare drafts side by side using the history panel on the right. Pick the version you like and promote it to the editor.',
  },
  {
    icon: Scissors,
    label: 'Editor',
    description:
      'The editor matches every storyboard scene to the best available footage segments and assembles a timeline. You can inspect the per-scene clip selections in the left panel, preview the result, and export the final cut as a single video file.',
  },
]

const steps = [
  {
    icon: FolderOpen,
    title: 'Create a project',
    body: 'Open the project dropdown in the top-left corner of the sidebar and click "New Project". Give it a name and press Enter. The project acts as a workspace that groups your footage, storyboards, and timelines together.',
  },
  {
    icon: Upload,
    title: 'Upload footage',
    body: 'Go to the Media tab and drag your video files onto the upload zone, or click to browse. You can upload multiple files at once. Each clip is queued for AI analysis — a spinner indicates work in progress. Wait until all clips have been processed before moving on.',
  },
  {
    icon: Sparkles,
    title: 'Generate a storyboard',
    body: 'Switch to the Storyboard tab and type a brief in the chat box — describe the story, tone, or key messages you want the video to convey. Submit it and the AI will produce a structured scene list. Review the scenes; if the result is not quite right, refine your brief and generate again. Previous versions are always accessible in the history sidebar.',
  },
  {
    icon: Clapperboard,
    title: 'Build and export the timeline',
    body: 'Once you are happy with a storyboard version, click "Use this storyboard" to send it to the editor. In the Editor tab, trigger a timeline build. The AI maps each scene to the most suitable footage segments. Review the assembly in the scene panel, preview the video, then hit Export to render the final file.',
  },
]

export default function HelpPage() {
  return (
    <div className="max-w-2xl mx-auto px-8 py-10 space-y-10">
      {/* Intro */}
      <section>
        <h1 className="text-xl font-semibold text-text-primary mb-3">AI Video Cutter</h1>
        <p className="text-sm text-muted leading-relaxed">
          AI Video Cutter turns raw footage into a finished cut using a three-step AI pipeline.
          Upload your clips, describe what you want, and let the models handle scene selection and
          assembly. The entire workflow lives in three tabs — Media, Storyboard, and Editor — each
          corresponding to one stage of the process.
        </p>
      </section>

      {/* Tabs */}
      <section>
        <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wider mb-4">
          The three tabs
        </h2>
        <div className="space-y-4">
          {tabs.map(({ icon: Icon, label, description }) => (
            <div key={label} className="flex gap-4 p-4 rounded-xl bg-bg-surface border border-border/20">
              <div className="shrink-0 mt-0.5">
                <div className="w-8 h-8 rounded-lg bg-accent/10 flex items-center justify-center">
                  <Icon size={16} className="text-accent" />
                </div>
              </div>
              <div>
                <p className="text-sm font-medium text-text-primary mb-1">{label}</p>
                <p className="text-sm text-muted leading-relaxed">{description}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Getting started */}
      <section>
        <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wider mb-4">
          Getting started
        </h2>
        <div className="space-y-0">
          {steps.map(({ icon: Icon, title, body }, i) => (
            <div key={title} className="flex gap-4">
              {/* Step spine */}
              <div className="flex flex-col items-center shrink-0">
                <div className="w-8 h-8 rounded-full bg-bg-surface border border-border/30 flex items-center justify-center shrink-0">
                  <Icon size={15} className="text-accent" />
                </div>
                {i < steps.length - 1 && (
                  <div className="w-px flex-1 bg-border/20 my-1" />
                )}
              </div>
              {/* Content */}
              <div className={`pb-6 ${i === steps.length - 1 ? 'pb-0' : ''}`}>
                <p className="text-sm font-medium text-text-primary mb-1 mt-1">{title}</p>
                <p className="text-sm text-muted leading-relaxed">{body}</p>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
