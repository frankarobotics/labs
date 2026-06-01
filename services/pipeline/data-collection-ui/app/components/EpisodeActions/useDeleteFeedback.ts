import { useCallback } from 'react'
import type { FetcherWithComponents } from 'react-router'
import { useNavigate } from 'react-router'

import { useToast } from '@/components/Toasts'
import useOnFetcherSuccess from '@/utils/useOnFetcherSuccess'

export default function useDeleteFeedback(fetcher: FetcherWithComponents<unknown>) {
  const toast = useToast()
  const navigate = useNavigate()
  const triggerDeletionFeedback = useCallback(() => {
    toast.show('Deleted episode')
    navigate('/episodes')
  }, [toast, navigate])
  useOnFetcherSuccess(fetcher, triggerDeletionFeedback)
}
