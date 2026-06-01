import { useEffect, useRef } from 'react'
import type { FetcherWithComponents } from 'react-router'

export default function useOnFetcherSuccess<TData>(fetcher: FetcherWithComponents<TData>, onSuccess: () => void) {
  const submitting = fetcher.state === 'submitting'
  const previouslySubmitting = useRef(false)

  useEffect(() => {
    if (!submitting && previouslySubmitting.current) {
      onSuccess()
    }
    previouslySubmitting.current = submitting
  }, [onSuccess, submitting])
}
