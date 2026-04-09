/**
 * Build URLs for video files served from the FastAPI /files/ static mount.
 *
 * Manifest filenames follow the pattern: `{stem}_original.MP4`
 * Downsampled files follow: `{stem}_downsampled.mp4`
 */

export function getDownsampledUrl(project: string, hash: string, filename: string): string {
  const stem = filename.replace(/_original\.\w+$/i, '')
  return `/files/${project}/videos/${hash}/${stem}_downsampled.mp4`
}

export function getOriginalUrl(project: string, hash: string, filename: string): string {
  return `/files/${project}/videos/${hash}/${filename}`
}
