import { data } from 'react-router'

import { CookieScope } from '@/sessions/CookieScope'
import { getTask } from '@/sessions/task'
import unwrapOrThrow from '@/utils/unwrapOrThrow'

import type { Route } from './+types/record-start'

export async function action({ request, context: { DATA_COLLECTION_CLIENT: client } }: Route.ActionArgs) {
  const cookieScope = new CookieScope(request)

  const task_id = await getTask(cookieScope)

  await unwrapOrThrow(
    client.POST('/api/v1/recording/start', {
      params: {
        query: {
          task_id,
        },
      },
    }),
  )

  return data(
    {},
    {
      status: 200,
    },
  )
}
