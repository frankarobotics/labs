import type { Route } from './+types/record-stop'

export async function action({ context: { DATA_COLLECTION_CLIENT: client } }: Route.ActionArgs) {
  return await client.POST('/api/v1/recording/stop', {})
}
