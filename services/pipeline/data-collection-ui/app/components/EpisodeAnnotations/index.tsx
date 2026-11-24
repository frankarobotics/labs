import clsx from 'clsx'
import { ChevronRight, CircleCheck, Download, ExternalLink } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useFetcher } from 'react-router'

import type { AnnotationStatus, StationAccount } from '@/api/annotations'
import Button, { ButtonLink } from '@/components/Button'

import ActionList from './ActionList'
import { lanes } from './actions'
import Billing from './Billing'
import { NOMADIC_BUTTON } from './nomadicButton'
import NomadicMark from './NomadicMark'
import Progress from './Progress'
import Setup from './Setup'
import Timeline from './Timeline'

const ACTIVE_STATES = new Set(['queued', 'preparing', 'uploading', 'ingesting', 'indexing', 'fetching'])

// Which account receives this station's uploads
function Connected({ account }: { account: StationAccount }) {
  return (
    <div>
      <p className='text text-positive-600 flex items-center gap-1.5'>
        <CircleCheck aria-hidden className='h-4 w-4' /> Connected to Nomadic as {account.email ?? 'your account'}
      </p>
      <p className='text text-adriatic-500 text-xs'>
        Uses the key file saved on this station. An administrator can remove the key file to disconnect.
      </p>
    </div>
  )
}

// Remembered per browser, so a station that hides the panel keeps it hidden across episodes
const COLLAPSED_KEY = 'nomadic-annotations-collapsed'

function Panel({ summary, children }: { summary?: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(true)
  useEffect(() => {
    try {
      setOpen(localStorage.getItem(COLLAPSED_KEY) !== 'true')
    } catch {
      // Storage can be unavailable; the panel then starts open.
    }
  }, [])
  const toggle = () => {
    setOpen(!open)
    try {
      localStorage.setItem(COLLAPSED_KEY, String(open))
    } catch {
      // Collapsing still works for this page.
    }
  }

  return (
    <section aria-labelledby='annotations-title' className='flex flex-col gap-3'>
      <div className='flex flex-wrap items-center justify-between gap-2'>
        <h2 id='annotations-title' className='header'>
          <button
            type='button'
            aria-expanded={open}
            aria-controls='annotations-body'
            onClick={toggle}
            className='keyboard-focus flex items-center gap-2 rounded-sm'
          >
            <ChevronRight aria-hidden className={clsx('h-5 w-5 transition-transform', open && 'rotate-90')} />
            Action annotations
            {!open && summary && <span className='text text-adriatic-500 font-normal'>· {summary}</span>}
          </button>
        </h2>
        <span className='text text-adriatic-500 flex items-center gap-1'>
          by <NomadicMark className='text-franka-blue h-3.5 w-3.5' /> Nomadic
        </span>
      </div>
      {open && (
        <div id='annotations-body' className='flex flex-col gap-3'>
          {children}
        </div>
      )}
    </section>
  )
}

function summaryOf(status: AnnotationStatus, active: boolean): string | undefined {
  if (status.setup) return 'Not connected'
  if (active) return 'In progress'
  if (status.job?.state === 'completed') return `${status.job.events.length} actions`
  if (status.job?.billing === 'out_of_credits') return 'Out of credits'
  if (status.job?.billing === 'uploads_not_enabled') return 'Uploads not enabled'
  if (status.job) return 'Needs attention'
  return undefined
}

export default function EpisodeAnnotations({ id, initialStatus }: { id: string; initialStatus: AnnotationStatus }) {
  const fetcher = useFetcher<{ status?: AnnotationStatus; error?: string }>()
  const status = initialStatus
  const job = status.job
  const active = !!job && ACTIVE_STATES.has(job.state)
  const endpoint = `/api/annotations?episode_id=${encodeURIComponent(id)}`
  const { state } = fetcher

  // The annotator decides when an episode with earlier remote work may be started again.
  const canStart = status.can_submit && !active && job?.state !== 'completed'

  if (!status.enabled) return null
  if (status.setup) {
    return (
      <Panel summary={summaryOf(status, active)}>
        <Setup setup={status.setup} endpoint={endpoint} />
      </Panel>
    )
  }

  return (
    <Panel summary={summaryOf(status, active)}>
      {status.account && <Connected account={status.account} />}
      {!active && job?.state !== 'completed' && (
        <p className='text max-w-[80ch]'>
          Analyze this saved recording with Nomadic to find timestamped robot actions.
        </p>
      )}
      {status.message && (
        <p className='text' role='status'>
          {status.message}
        </p>
      )}
      {!active && job?.billing && (
        <Billing
          job={{ ...job, billing: job.billing }}
          billingUrl={status.billing_url}
          canResume={!!status.can_resume}
          endpoint={endpoint}
        />
      )}
      {canStart && (
        <fetcher.Form method='post' action={endpoint}>
          <button className={NOMADIC_BUTTON} type='submit' disabled={state !== 'idle'}>
            <NomadicMark className='h-4 w-4' /> {job?.remote_started ? 'Start again' : 'Auto Annotate with Nomadic'}
          </button>
        </fetcher.Form>
      )}
      {!active && status.can_resume && !job?.billing && (
        <fetcher.Form method='post' action={endpoint}>
          <input type='hidden' name='intent' value='refresh' />
          <Button variant='outline' type='submit' disabled={state !== 'idle'}>
            {job?.analysis_id || job?.batch_id ? 'Refresh saved result' : 'Continue with the saved upload'}
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
          {active ? (
            <Progress state={job.state} message={job.message} />
          ) : (
            !job.billing && (
              <p className='text' role='status' aria-live='polite'>
                {job.message}
              </p>
            )
          )}
          {(job.viewer_url || job.state === 'completed') && (
            <div className='flex flex-wrap items-center gap-3'>
              {job.viewer_url && (
                <ButtonLink variant='outline' href={job.viewer_url} target='_blank' rel='noreferrer'>
                  <ExternalLink aria-hidden className='h-4 w-4' /> Open in Nomadic Workbench
                </ButtonLink>
              )}
              {job.state === 'completed' && (
                <ButtonLink variant='outline' href={`${endpoint}&download=1`}>
                  <Download aria-hidden className='h-4 w-4' /> Download annotations
                </ButtonLink>
              )}
            </div>
          )}
          {job.state === 'completed' &&
            (job.events.length > 0 ? (
              <div className='flex flex-col gap-5'>
                <Timeline lanes={lanes(job.events)} />
                <ActionList lanes={lanes(job.events)} />
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
    </Panel>
  )
}
