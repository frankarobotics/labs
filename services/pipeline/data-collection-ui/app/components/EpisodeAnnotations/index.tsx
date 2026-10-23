import { Download, Send } from 'lucide-react'
import { useFetcher } from 'react-router'

import type { AnnotationEvent, AnnotationStatus } from '@/api/annotations'
import Button from '@/components/Button'

const ACTIVE_STATES = new Set(['queued', 'preparing', 'uploading', 'ingesting', 'indexing', 'fetching'])

function ActionDetails({ event }: { event: AnnotationEvent }) {
  const transitions = event.gripper_transitions ?? []
  const interactions = event.object_interactions ?? []
  if (!transitions.length && !interactions.length) return null

  return (
    <details className='mt-3'>
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

export default function EpisodeAnnotations({ id, initialStatus }: { id: string; initialStatus: AnnotationStatus }) {
  const fetcher = useFetcher<{ status?: AnnotationStatus; error?: string }>()
  const status = initialStatus
  const job = status.job
  const active = !!job && ACTIVE_STATES.has(job.state)
  const endpoint = `/api/annotations?episode_id=${encodeURIComponent(id)}`
  const { state } = fetcher

  const canStart = status.can_submit && !active && !job?.remote_started && job?.state !== 'completed'
  const showHand = job?.events.some((event) => !!event.acting_hand) ?? false
  const showObjects = job?.events.some((event) => event.objects.length > 0) ?? false

  if (!status.enabled) return null

  return (
    <section aria-labelledby='annotations-title' className='flex flex-col gap-3'>
      <h2 id='annotations-title' className='header'>
        Action annotations
      </h2>
      {job?.state !== 'completed' && (
        <p className='text max-w-[80ch]'>
          Analyze this saved recording with Nomadic to find timestamped robot actions.
        </p>
      )}
      {status.message && (
        <p className='text' role='status'>
          {status.message}
        </p>
      )}
      {canStart && (
        <fetcher.Form method='post' action={endpoint}>
          <Button variant='primary' type='submit' disabled={state !== 'idle'}>
            <Send aria-hidden className='h-4 w-4' /> Auto Annotate with Nomadic
          </Button>
        </fetcher.Form>
      )}
      {!active && job?.state === 'interrupted' && job.video_id && (job.analysis_id || job.batch_id) && (
        <fetcher.Form method='post' action={endpoint}>
          <input type='hidden' name='intent' value='refresh' />
          <Button variant='outline' type='submit' disabled={state !== 'idle'}>
            Refresh saved result
          </Button>
        </fetcher.Form>
      )}
      {fetcher.data?.error && !active && job?.state !== 'completed' && (
        <p className='text' role='alert'>
          {fetcher.data.error}
        </p>
      )}
      {job && (
        <>
          <p className='text' role='status' aria-live='polite'>
            {job.message}
          </p>
          {job.warnings.length > 0 && (
            <ul className='text list-inside list-disc'>
              {job.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          )}
          {(job.viewer_url || job.state === 'completed') && (
            <div className='flex flex-wrap items-center gap-x-5 gap-y-2'>
              {job.viewer_url && (
                <a className='text keyboard-focus underline' href={job.viewer_url} target='_blank' rel='noreferrer'>
                  Open in Nomadic Workbench
                </a>
              )}
              {job.state === 'completed' && (
                <a
                  className='text keyboard-focus inline-flex items-center gap-2 underline'
                  href={`${endpoint}&download=1`}
                >
                  <Download aria-hidden className='h-4 w-4' /> Download annotations
                </a>
              )}
            </div>
          )}
          {job.state === 'completed' &&
            (job.events.length > 0 ? (
              <div className='overflow-x-auto'>
                <table className='text w-full border-collapse text-left'>
                  <caption className='pb-3 text-left'>Times are seconds from the recording start.</caption>
                  <thead>
                    <tr>
                      {[
                        'Start',
                        'End',
                        'Action',
                        ...(showHand ? ['Hand'] : []),
                        ...(showObjects ? ['Objects'] : []),
                      ].map((label) => (
                        <th key={label} scope='col' className='border-pastel-grey-300 border-b p-2'>
                          {label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className='divide-pastel-grey-300 divide-y'>
                    {job.events.map((event) => (
                      <tr key={event.event_id}>
                        <td className='p-2 align-top tabular-nums'>{event.start_seconds.toFixed(3)}</td>
                        <td className='p-2 align-top tabular-nums'>{event.end_seconds.toFixed(3)}</td>
                        <td className='p-2 align-top'>
                          <p>{event.description}</p>
                          <div className='mt-2 flex flex-wrap gap-1'>
                            {(event.action_classes?.length
                              ? event.action_classes
                              : event.category
                                ? [event.category]
                                : []
                            ).map((category) => (
                              <span
                                key={category}
                                className='border-pastel-grey-300 bg-pastel-grey-100 inline-block rounded-sm border px-2 py-1 text-xs font-medium'
                              >
                                {category}
                              </span>
                            ))}
                          </div>
                          <ActionDetails event={event} />
                        </td>
                        {showHand && <td className='p-2 align-top'>{event.acting_hand ?? 'Unknown'}</td>}
                        {showObjects && <td className='p-2 align-top'>{event.objects.join(', ') || '—'}</td>}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className='text'>No action windows were returned for this recording.</p>
            ))}
          {(job.ingest_id || job.video_id || job.index_run_id) && (
            <details className='text'>
              <summary className='keyboard-focus cursor-pointer'>Nomadic references</summary>
              <dl className='mt-2 grid gap-2 break-all'>
                {(
                  [
                    ['Upload', job.ingest_id],
                    ['Video', job.video_id],
                    ['Batch', job.batch_id],
                    ['Annotation run', job.index_run_id],
                    ['Analysis', job.analysis_id],
                  ] as const
                )
                  .filter(([, value]) => value)
                  .map(([label, value]) => (
                    <div key={label}>
                      <dt className='font-medium'>{label}</dt>
                      <dd>{value}</dd>
                    </div>
                  ))}
              </dl>
            </details>
          )}
        </>
      )}
    </section>
  )
}
