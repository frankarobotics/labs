import clsx from 'clsx'

import type { AnnotationEvent } from '@/api/annotations'

import { actionColor, actionLabels, type Lane, timeRange } from './actions'

function ActionDetails({ event }: { event: AnnotationEvent }) {
  const transitions = event.gripper_transitions ?? []
  const interactions = event.object_interactions ?? []
  if (!transitions.length && !interactions.length) return null

  return (
    <details className='mt-2'>
      <summary className='keyboard-focus w-fit cursor-pointer text-sm'>Details</summary>
      <dl className='mt-2 grid gap-3 text-sm'>
        {transitions.length > 0 && (
          <div>
            <dt className='font-medium'>Gripper transitions</dt>
            <dd>{transitions.join(', ')}</dd>
          </div>
        )}
        {interactions.length > 0 && (
          <div>
            <dt className='font-medium'>Object interactions</dt>
            <dd>
              <ul className='list-inside list-disc'>
                {interactions.map((interaction) => {
                  const label = typeof interaction === 'string' ? interaction : JSON.stringify(interaction)
                  return <li key={label}>{label}</li>
                })}
              </ul>
            </dd>
          </div>
        )}
      </dl>
    </details>
  )
}

export default function ActionList({ lanes }: { lanes: Lane[] }) {
  return (
    <div className='flex flex-col gap-4'>
      {lanes.map((lane) => (
        <div key={lane.label}>
          <h3 className='text border-pastel-grey-300 border-b pb-1 font-semibold'>{lane.label}</h3>
          <ul className='divide-pastel-grey-300 divide-y'>
            {lane.events.map((event) => (
              <li
                key={event.event_id}
                id={`action-${event.event_id}`}
                className='text target:bg-deep-sky-100 grid scroll-mt-4 grid-cols-[10.5rem_1fr] gap-3 py-2'
              >
                <span className='text-adriatic-500 tabular-nums'>{timeRange(event)}</span>
                <div>
                  <div className='flex flex-wrap items-center gap-1'>
                    {actionLabels(event).map((label) => (
                      <span
                        key={label}
                        className={clsx('rounded-sm px-2 py-0.5 text-xs font-semibold', actionColor(label))}
                      >
                        {label}
                      </span>
                    ))}
                    {event.objects.length > 0 && (
                      <span className='text-adriatic-500 ml-1 text-xs'>{event.objects.join(', ')}</span>
                    )}
                  </div>
                  <p className='mt-1'>{event.description}</p>
                  <ActionDetails event={event} />
                </div>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  )
}
