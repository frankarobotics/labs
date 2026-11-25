import { data } from 'react-router'

import { type AnnotationJob, annotationStatus, annotationUrl, type StationAccount } from '@/api/annotations'

import type { Route } from './+types/annotations'

function episodeId(request: Request) {
  const id = new URL(request.url).searchParams.get('episode_id')
  if (!id || !/^[\da-f]{8}-[\da-f]{4}-7[\da-f]{3}-[89ab][\da-f]{3}-[\da-f]{12}$/i.test(id)) {
    throw data({ error: 'A valid episode identifier is required.' }, { status: 400 })
  }
  return id
}

function annotator(base: URL | null) {
  if (!base) throw data({ error: 'Nomadic annotations are not configured.' }, { status: 404 })
  return base
}

// The key goes to the annotator over loopback; it is not logged here or sent back to the browser
async function connect(base: URL, apiKey: FormDataEntryValue | null) {
  try {
    const response = await fetch(new URL('/api/v1/station/api-key', base), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: typeof apiKey === 'string' ? apiKey : '' }),
      signal: AbortSignal.timeout(30000),
    })
    const body: { detail?: unknown } = await response.json()
    if (!response.ok) {
      return data(
        { error: typeof body.detail === 'string' ? body.detail : 'The key could not be checked. Try again.' },
        { status: response.status },
      )
    }
    return data({ account: body as StationAccount })
  } catch {
    return data({ error: 'The key could not be checked. Try again.' }, { status: 503 })
  }
}

export async function loader({ request, context: { NOMADIC_EPISODE_ANNOTATOR_URL } }: Route.LoaderArgs) {
  const base = annotator(NOMADIC_EPISODE_ANNOTATOR_URL)
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

export async function action({ request, context: { NOMADIC_EPISODE_ANNOTATOR_URL } }: Route.ActionArgs) {
  const base = annotator(NOMADIC_EPISODE_ANNOTATOR_URL)
  const id = episodeId(request)
  const form = await request.formData()
  const intent = form.get('intent')
  if (intent === 'connect') return connect(base, form.get('api_key'))
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
