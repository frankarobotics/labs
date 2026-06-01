import { data } from 'react-router'

import { CookieScope } from '@/sessions/CookieScope'
import { setTaskId } from '@/sessions/task'

import type { Route } from './+types/task'

export async function action({ request }: Route.ActionArgs) {
  const formData = await request.formData()

  const newTask = formData.get('task')

  if (typeof newTask !== 'string') throw new Error(`Unexpected format on type change payload: ${newTask}`)

  const cookieScope = new CookieScope(request)

  await setTaskId(cookieScope, newTask)

  return data({}, { status: 200, headers: cookieScope.headers })
}
