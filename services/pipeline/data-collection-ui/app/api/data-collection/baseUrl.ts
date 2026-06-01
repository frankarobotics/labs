import { readFileSync } from 'fs'

import type { Request as ExpressRequest } from 'express'
import yaml from 'js-yaml'

const CONFIG_FILE =
  process.env.DATA_COLLECTION_CONFIG_FILE ?? '/workspace/config_data_collection.yml'

function loadDataCollectionPort(): string {
  try {
    const raw = yaml.load(readFileSync(CONFIG_FILE, 'utf-8')) as Record<string, unknown>
    const section = raw?.data_collection as Record<string, unknown> | undefined
    const url = (section?.url as string | undefined) ?? '0.0.0.0:3001'
    return url.split(':').at(-1) ?? '3001'
  } catch {
    return '3001'
  }
}

const DATA_COLLECTION_PORT = loadDataCollectionPort()

export function resolveBaseUrl(req: ExpressRequest): URL {
  const protocol = req.get('x-forwarded-proto') ?? req.protocol
  const host = req.get('x-forwarded-host') ?? req.host

  const url = new URL(`${protocol}://${host}`)
  url.port = DATA_COLLECTION_PORT

  return url
}
