import type { Client } from 'openapi-fetch'
import { createCookie } from 'react-router'

import type { paths } from '@/api/data-collection/types'
import unwrapOrThrow from '@/utils/unwrapOrThrow'

import base from './base'
import type { CookieScope } from './CookieScope'

export type TaskID = string

const taskCookie = createCookie('task_id', {
  ...base,
})

export async function verifyTask(
  cookieScope: CookieScope,
  client: Client<paths, `${string}/${string}`>,
): Promise<void> {
  let cookieValue: string | null = null
  const parsedCookie = await cookieScope.get(taskCookie)
  if (parsedCookie !== null && typeof parsedCookie !== 'string') {
    console.log('Unexpected task cookie format:', parsedCookie)
  } else {
    cookieValue = parsedCookie
  }

  const tasks = await unwrapOrThrow(client.GET('/api/v1/tasks'))

  const byId = (id: string | null) => (id ? tasks.find((t) => t.task_id === id) : undefined)

  // if a cookie is set, ensure it points to an actual task
  if (typeof cookieValue === 'string') {
    const task = byId(cookieValue)
    if (task) {
      // the cookie is valid → Keep it.
      await cookieScope.set(taskCookie, task.task_id)
      return
    }
    // invalid / mismatched cookie → clear, then fall through to selection logic.
    await cookieScope.clear(taskCookie)
  }

  // No valid cookie at this point → choose any task id.

  // Data Collection service guarantees that at least one (dummy) task exists.
  if (tasks.length === 0) throw new Error('No task found!')

  await cookieScope.set(taskCookie, tasks[0].task_id)
}

export async function setTaskId(cookieScope: CookieScope, taskId: TaskID): Promise<void> {
  return cookieScope.set(taskCookie, taskId)
}

export async function getTask(cookieScope: CookieScope): Promise<TaskID> {
  const cookieValue = await cookieScope.get(taskCookie)

  if (typeof cookieValue !== 'string') throw new Error('Parsing error while parsing task cookie')

  return cookieValue as TaskID
}

export default taskCookie
