import { CircleAlert, CreditCard, RotateCw } from 'lucide-react'
import { useFetcher } from 'react-router'

import type { AnnotationJob } from '@/api/annotations'
import Button from '@/components/Button'

import { NOMADIC_BUTTON } from './nomadicButton'

const COPY = {
  out_of_credits: { title: 'Not enough Nomadic credits', action: 'Top up credits' },
  uploads_not_enabled: { title: 'Uploads are not enabled for this Nomadic account', action: 'Open Nomadic billing' },
}

// Nomadic declined the work for billing reasons; nothing was charged, and the operator can fix it and retry
export default function Billing({
  job,
  billingUrl,
  canResume,
  endpoint,
}: {
  job: AnnotationJob & { billing: keyof typeof COPY }
  billingUrl: string | null | undefined
  canResume: boolean
  endpoint: string
}) {
  const fetcher = useFetcher()

  return (
    <div role='alert' className='border-critical-peach-500 bg-critical-peach-200 flex gap-3 rounded-[10px] border p-4'>
      <CircleAlert aria-hidden className='text-critical-peach-600 mt-0.5 h-5 w-5 shrink-0' />
      <div className='flex flex-col gap-3'>
        <div>
          <p className='text font-semibold'>{COPY[job.billing].title}</p>
          <p className='text max-w-[80ch]'>{job.message}</p>
        </div>
        <div className='flex flex-wrap items-center gap-3'>
          {billingUrl && (
            <a className={NOMADIC_BUTTON} href={billingUrl} target='_blank' rel='noreferrer'>
              <CreditCard aria-hidden className='h-4 w-4' /> {COPY[job.billing].action}
            </a>
          )}
          {canResume && (
            <fetcher.Form method='post' action={endpoint}>
              <input type='hidden' name='intent' value='refresh' />
              <Button variant='outline' type='submit' disabled={fetcher.state !== 'idle'}>
                <RotateCw aria-hidden className='h-4 w-4' /> Retry annotation
              </Button>
            </fetcher.Form>
          )}
        </div>
      </div>
    </div>
  )
}
