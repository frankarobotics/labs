import { data } from 'react-router'

import unwrapOrThrow from '@/utils/unwrapOrThrow'

import type { Route } from './+types/follower-reset'

export async function action({ context: { DATA_COLLECTION_CLIENT: client } }: Route.ActionArgs) {
  try {
    const result = await unwrapOrThrow(client.POST('/api/v1/teleop/start_syncing', { signal: AbortSignal.timeout(5_000) }))
    return data({}, { status: result.success ? 200 : 400 })
  } catch (err: unknown) {
    if (typeof err !== 'object' || err === null) throw err

    if (err instanceof DOMException && err.name === 'TimeoutError') {
      await unwrapOrThrow(client.POST('/api/v1/teleop/stop'))
      await unwrapOrThrow(client.POST('/api/v1/teleop/start'))
      return data({ error: 'Sync timed out, teleoperation restarted' }, { status: 500 })
    }

    // Upstream returned an HTTP error (e.g. 500 from DC when coordinators are IDLE).
    // DataWithResponseInit thrown by unwrapOrThrow has shape { type, data, init: { status } }.
    // Return it as a handled response so the fetcher reaches `idle` with data,
    // allowing the UI to refresh button states.
    if (
      typeof err === 'object' &&
      'type' in err &&
      (err as Record<string, unknown>).type === 'DataWithResponseInit'
    ) {
      return data({ error: 'Sync failed, robots may not be ready' }, { status: 500 })
    }

    throw err
  }
}
