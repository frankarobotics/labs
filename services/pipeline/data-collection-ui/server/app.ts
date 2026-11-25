import 'react-router'

import { createRequestHandler } from '@react-router/express'
import express from 'express'
import createClient, { type Client } from 'openapi-fetch'

import { annotatorBaseUrl } from '../app/api/annotator/baseUrl'
import { resolveBaseUrl } from '../app/api/data-collection/baseUrl'
import type { paths } from '../app/api/data-collection/types'

declare module 'react-router' {
  interface AppLoadContext {
    DATA_COLLECTION_URL: URL
    DATA_COLLECTION_CLIENT: Client<paths, `${string}/${string}`>
    NOMADIC_EPISODE_ANNOTATOR_URL: URL | null
  }
}

export const app = express()

const NOMADIC_EPISODE_ANNOTATOR_URL = annotatorBaseUrl(process.env.NOMADIC_EPISODE_ANNOTATOR_PORT)

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
        NOMADIC_EPISODE_ANNOTATOR_URL,
      }
    },
  }),
)
