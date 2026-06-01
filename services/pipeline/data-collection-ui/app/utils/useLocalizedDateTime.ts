import { useMemo } from 'react'

const LOCALE = undefined
// uncomment to test locales
// const LOCALE = 'en-US'
// const LOCALE = 'de-DE'
// const LOCALE = 'ja-JP'

export default function useLocalizedDateTime(iso: string | undefined | null) {
  return useMemo(() => {
    if (!iso) return { date: 'unknown', time: 'unknown' }
    const d = new Date(iso)

    const date = new Intl.DateTimeFormat(LOCALE, {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).format(d)

    const time = new Intl.DateTimeFormat(LOCALE, {
      hour: '2-digit',
      minute: '2-digit',
    }).format(d)

    return { date, time }
  }, [iso])
}
