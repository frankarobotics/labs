import { redirect } from 'react-router'

import unwrapOrThrow from '@/utils/unwrapOrThrow'

import type { Route } from './+types/episode'

export async function action({ request, context: { DATA_COLLECTION_CLIENT: client } }: Route.ActionArgs) {
  const formData = await request.formData()
  const action = formData.get('_action')
  const id = formData.get('_id')

  if (typeof id !== 'string') return data({}, { status: 400 })

  await unwrapOrThrow(
    client.GET('/api/v1/episodes/{episode_id}', {
      params: { path: { episode_id: id } },
    }),
    {
      onHttpError: ({ response }) => {
        if (response.status === 404) throw data({}, { status: 404 })
      },
    },
  )

  if (action === 'delete') {
    await unwrapOrThrow(
      client.DELETE('/api/v1/episodes/{episode_id}', {
        params: { path: { episode_id: id } },
      }),
    )
    return redirect('/episodes')
  }
}
