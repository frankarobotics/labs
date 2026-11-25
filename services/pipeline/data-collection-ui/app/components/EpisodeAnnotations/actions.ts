import type { AnnotationEvent } from '@/api/annotations'
import secondsToMMSS from '@/utils/secondsToMMSS'

// One lane per acting hand; actions without a hand describe the whole scene
const LANES = [
  { hand: 'left', label: 'Left arm' },
  { hand: 'right', label: 'Right arm' },
  { hand: 'both', label: 'Both arms' },
  { hand: null, label: 'Scene' },
] as const

// Full class names so Tailwind keeps them in the build
const ACTION_COLORS: Record<string, string> = {
  Pick: 'bg-deep-sky-300',
  Transport: 'bg-information-300',
  Place: 'bg-positive-300',
  Idle: 'bg-pastel-grey-500',
  Other: 'bg-adriatic-200',
}

export type Lane = { label: string; events: AnnotationEvent[] }

export function lanes(events: AnnotationEvent[]): Lane[] {
  return LANES.map(({ hand, label }) => ({
    label,
    events: events
      .filter((event) => (event.acting_hand ?? null) === hand)
      .toSorted((a, b) => a.start_seconds - b.start_seconds),
  })).filter((lane) => lane.events.length > 0)
}

export function actionLabels(event: AnnotationEvent): string[] {
  if (event.action_classes?.length) return event.action_classes
  return event.category ? [event.category] : []
}

export function actionColor(label: string | undefined): string {
  return (label && ACTION_COLORS[label]) || 'bg-critical-lemon-300'
}

// mm:ss.SSS, since action boundaries matter to the millisecond when building training data
export function timestamp(seconds: number): string {
  const milliseconds = Math.round(seconds * 1000)
  return `${secondsToMMSS(Math.floor(milliseconds / 1000))}.${String(milliseconds % 1000).padStart(3, '0')}`
}

export function timeRange(event: AnnotationEvent): string {
  return `${timestamp(event.start_seconds)} – ${timestamp(event.end_seconds)}`
}
