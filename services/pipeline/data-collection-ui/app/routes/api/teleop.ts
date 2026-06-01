import { data } from 'react-router'

import type { Route } from './+types/teleop'

export async function action({ request, context: { DATA_COLLECTION_CLIENT: client } }: Route.ActionArgs) {
  const operation = (await request.formData()).get('operation')

  if (operation !== 'stop' && operation !== 'start') throw new Error(`Unknown operation ${operation} in /api/teleop`)

  const result = await client.POST(`/api/v1/teleop/${operation}`)
  return data(result, { status: result.response.ok ? 200 : 400 })
}
