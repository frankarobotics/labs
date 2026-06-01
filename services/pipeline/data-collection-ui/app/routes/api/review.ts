import { data } from 'react-router'

import unwrapOrThrow from '@/utils/unwrapOrThrow'

import type { Route } from './+types/review'

const RESOLUTION_TO_LABEL = {
  rejected: 'REVIEW_FAILED',
  accepted: 'REVIEW_SUCCESS',
} as const

export async function action({ request, context: { DATA_COLLECTION_CLIENT: client } }: Route.ActionArgs) {
  const resolution = (await request.formData()).get('resolution')

  if (resolution !== 'accepted' && resolution !== 'rejected' && resolution !== 'discarded')
    throw new Error(`Unknown resolution ${resolution} in /api/review`)

  if (resolution === 'discarded') {
    await unwrapOrThrow(
      client.POST('/api/v1/recording/discard', {}),
    )
  } else {
    await unwrapOrThrow(
      client.POST('/api/v1/recording/save', {
        params: { query: { label: RESOLUTION_TO_LABEL[resolution as 'accepted' | 'rejected'] } },
      }),
    )
  }

  return data(
    { resolution },
    {
      status: 200,
    },
  )
}
