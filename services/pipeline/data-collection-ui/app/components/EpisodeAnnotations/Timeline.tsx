import clsx from 'clsx'

import type { AnnotationEvent } from '@/api/annotations'
import secondsToMMSS from '@/utils/secondsToMMSS'

import { actionColor, actionLabels, type Lane, timeRange } from './actions'

const ROW_HEIGHT_REM = 1.75
const TICK_STEPS = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600]

// Stack overlapping actions in a lane onto separate rows
function rows(events: AnnotationEvent[]) {
  const rowEnds: number[] = []
  return events.map((event) => {
    let row = rowEnds.findIndex((end) => end <= event.start_seconds)
    if (row === -1) row = rowEnds.push(0) - 1
    rowEnds[row] = event.end_seconds
    return { event, row }
  })
}

function ticks(duration: number) {
  const step = TICK_STEPS.find((candidate) => duration / candidate <= 6) ?? TICK_STEPS.at(-1)!
  return Array.from({ length: Math.floor(duration / step) + 1 }, (_, index) => index * step)
}

export default function Timeline({ lanes }: { lanes: Lane[] }) {
  const duration = Math.max(...lanes.flatMap((lane) => lane.events.map((event) => event.end_seconds))) || 1
  const percent = (seconds: number) => `${(seconds / duration) * 100}%`

  return (
    <div className='grid grid-cols-[6rem_1fr] items-start gap-x-3 gap-y-2'>
      {lanes.map((lane) => {
        const placed = rows(lane.events)
        const rowCount = Math.max(...placed.map(({ row }) => row)) + 1
        return [
          <span key={`${lane.label}-label`} className='text py-1'>
            {lane.label}
          </span>,
          <div
            key={`${lane.label}-track`}
            className='bg-pastel-grey-200 relative rounded-sm'
            style={{ height: `${rowCount * ROW_HEIGHT_REM}rem` }}
          >
            {placed.map(({ event, row }) => {
              const label = actionLabels(event).join(', ') || 'Action'
              return (
                <a
                  key={event.event_id}
                  href={`#action-${event.event_id}`}
                  title={`${label}, ${timeRange(event)}: ${event.description}`}
                  className={clsx(
                    'keyboard-focus text absolute truncate rounded-sm border border-white px-2 leading-7 hover:brightness-95',
                    actionColor(actionLabels(event)[0]),
                  )}
                  style={{
                    left: percent(event.start_seconds),
                    width: percent(event.end_seconds - event.start_seconds),
                    top: `${row * ROW_HEIGHT_REM}rem`,
                    height: `${ROW_HEIGHT_REM}rem`,
                  }}
                >
                  {label}
                </a>
              )
            })}
          </div>,
        ]
      })}
      <div className='text-adriatic-500 relative col-start-2 h-4 text-xs tabular-nums'>
        {ticks(duration).map((seconds) => (
          <span
            key={seconds}
            className='absolute -translate-x-1/2 first:translate-x-0'
            style={{ left: percent(seconds) }}
          >
            {secondsToMMSS(seconds)}
          </span>
        ))}
      </div>
    </div>
  )
}
