import { data } from 'react-router'

import { type AnnotationJob, annotationStatus, annotationUrl } from '@/api/annotations'

import type { Route } from './+types/annotations'

function episodeId(request: Request) {
  const id = new URL(request.url).searchParams.get('episode_id')
  if (!id || !/^[\da-f]{8}-[\da-f]{4}-7[\da-f]{3}-[89ab][\da-f]{3}-[\da-f]{12}$/i.test(id)) {
    throw data({ error: 'A valid episode identifier is required.' }, { status: 400 })
  }
  return id
}

export async function loader({ request, context: { DATA_COLLECTION_URL: base } }: Route.LoaderArgs) {
  const id = episodeId(request)
  if (new URL(request.url).searchParams.has('download')) {
    const response = await fetch(annotationUrl(base, id, true), { signal: AbortSignal.timeout(10000) })
    if (!response.ok) throw data({ error: 'Annotations are not available.' }, { status: response.status })
    return new Response(response.body, {
      headers: {
        'Content-Type': 'application/json',
        'Content-Disposition': `attachment; filename="${id}-annotations.json"`,
      },
    })
  }
  return data({ status: await annotationStatus(base, id) }, { headers: { 'Cache-Control': 'no-store' } })
}

export async function action({ request, context: { DATA_COLLECTION_URL: base } }: Route.ActionArgs) {
  const id = episodeId(request)
  const intent = (await request.formData()).get('intent')
  const target = annotationUrl(base, id)
  if (intent === 'refresh') target.pathname += '/refresh'
  try {
    const response = await fetch(target, { method: 'POST', signal: AbortSignal.timeout(10000) })
    if (!response.ok) {
      const body: { detail?: string } = await response.json()
      return data(
        { error: typeof body.detail === 'string' ? body.detail : 'Could not start annotation.' },
        { status: response.status },
      )
    }
    const job: AnnotationJob = await response.json()
    return data({ status: { enabled: true, can_submit: false, message: '', job } })
  } catch {
    return data({ error: 'The request could not be confirmed. Refresh status before trying again.' }, { status: 503 })
  }
}
