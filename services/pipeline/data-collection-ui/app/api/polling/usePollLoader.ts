import { useEffect } from 'react'
import { useRevalidator } from 'react-router'

export default function usePollLoader(POLL_INTERVAL = 200, poll = true) {
  const { revalidate, state } = useRevalidator()

  useEffect(() => {
    let id: ReturnType<typeof setInterval> | undefined

    const start = () => {
      id = setInterval(() => {
        if (state === 'idle') {
          revalidate()
        }
      }, POLL_INTERVAL)
    }

    const stop = () => {
      if (id) {
        clearInterval(id)
        id = undefined
      }
    }

    const handleVis = () => {
      if (document.visibilityState === 'visible') {
        if (state === 'idle') revalidate()
        start()
      } else {
        stop()
      }
    }

    if (poll) {
      document.addEventListener('visibilitychange', handleVis)
      if (document.visibilityState === 'visible') start()
    }

    return () => {
      stop()
      document.removeEventListener('visibilitychange', handleVis)
    }
  }, [poll, POLL_INTERVAL, revalidate, state])
}
