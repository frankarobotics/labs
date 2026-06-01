import 'react-router'

import { createRequestHandler } from '@react-router/express'
import express from 'express'
import createClient, { type Client } from 'openapi-fetch'

import { resolveBaseUrl } from '../app/api/data-collection/baseUrl'
import type { paths } from '../app/api/data-collection/types'

declare module 'react-router' {
  interface AppLoadContext {
    DATA_COLLECTION_URL: URL
    DATA_COLLECTION_CLIENT: Client<paths, `${string}/${string}`>
  }
}

export const app = express()

app.use(
  createRequestHandler({
    build: () => import('virtual:react-router/server-build'),
    getLoadContext(req) {
      const baseUrl = resolveBaseUrl(req)

      return {
        DATA_COLLECTION_URL: baseUrl,
        DATA_COLLECTION_CLIENT: createClient<paths>({
          baseUrl: baseUrl.href,
          headers: {
            'Content-Type': 'application/json',
          },
        }),
      }
    },
  }),
)
