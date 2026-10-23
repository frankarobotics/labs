export type AnnotationEvent = {
  event_id: string
  start_seconds: number
  end_seconds: number
  description: string
  category: string | null
  acting_hand: 'left' | 'right' | 'both' | null
  objects: string[]
  action_classes: string[]
  gripper_transitions: string[]
  object_interactions: (string | Record<string, unknown>)[]
  structured_output: Record<string, unknown>
}

export type AnnotationJob = {
  job_id: string
  episode_id: string
  state: string
  message: string
  remote_started: boolean
  ingest_id: string | null
  video_id: string | null
  batch_id: string | null
  index_run_id: string | null
  analysis_id: string | null
  viewer_url: string | null
  warnings: string[]
  events: AnnotationEvent[]
}

export type AnnotationStatus = { enabled: boolean; can_submit: boolean; message: string; job: AnnotationJob | null }

export function annotationUrl(base: URL, episodeId: string, download = false) {
  return new URL(`/api/v1/episodes/${encodeURIComponent(episodeId)}/annotations${download ? '/download' : ''}`, base)
}

export async function annotationStatus(base: URL, episodeId: string): Promise<AnnotationStatus> {
  try {
    const response = await fetch(annotationUrl(base, episodeId), { signal: AbortSignal.timeout(5000) })
    if (response.ok) return await response.json()
  } catch {
    // Annotation availability must not prevent the episode page from loading.
  }
  return {
    enabled: true,
    can_submit: false,
    message: 'Nomadic annotations are temporarily unavailable. Try again shortly.',
    job: null,
  }
}
