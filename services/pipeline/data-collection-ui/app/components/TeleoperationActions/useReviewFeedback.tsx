import { useCallback } from 'react'
import type { FetcherWithComponents } from 'react-router'

import { useToast } from '@/components/Toasts'
import useOnFetcherSuccess from '@/utils/useOnFetcherSuccess'

function resolutionToToast(resolution: string) {
  switch (resolution) {
    case 'rejected':
      return 'Recording saved as failed.'
    case 'accepted':
      return 'Recording saved as successful.'
    case 'discarded':
      return 'Recording discarded.'
    default:
      throw new Error('unknown resolution message!')
  }
}

export default function useReviewFeedback(fetcher: FetcherWithComponents<unknown>) {
  const toast = useToast()
  const reviewFeedback = useCallback(() => {
    if (
      fetcher.formAction !== '/api/review' ||
      typeof fetcher.data !== 'object' ||
      fetcher.data === null ||
      !('resolution' in fetcher.data) ||
      typeof fetcher.data.resolution !== 'string'
    )
      return
    toast.show(resolutionToToast(fetcher.data.resolution))
  }, [fetcher, toast])
  useOnFetcherSuccess(fetcher, reviewFeedback)
}
