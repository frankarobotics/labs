import clsx from 'clsx'
import { Check, LoaderCircle } from 'lucide-react'

// Job states in the order the annotator moves through them, grouped into the steps an operator sees
const STEPS = [
  { label: 'Prepare recording', states: ['queued', 'preparing'] },
  { label: 'Upload to Nomadic', states: ['uploading'] },
  { label: 'Process in Nomadic', states: ['ingesting'] },
  { label: 'Annotate actions', states: ['indexing', 'fetching'] },
]

export default function Progress({ state, message }: { state: string; message: string }) {
  const current = STEPS.findIndex((step) => step.states.includes(state))

  return (
    <div className='flex flex-col gap-3'>
      <ol className='flex flex-wrap gap-x-6 gap-y-2'>
        {STEPS.map((step, index) => (
          <li
            key={step.label}
            aria-current={index === current ? 'step' : undefined}
            className={clsx('text flex items-center gap-2', index > current && 'text-adriatic-300')}
          >
            <span
              className={clsx(
                'flex h-6 w-6 items-center justify-center rounded-full border-2',
                index < current && 'border-deep-sky bg-deep-sky text-white',
                index === current && 'border-deep-sky text-deep-sky',
                index > current && 'border-pastel-grey-500',
              )}
            >
              {index < current && <Check aria-hidden className='h-4 w-4' />}
              {index === current && <LoaderCircle aria-hidden className='h-4 w-4 animate-spin' />}
            </span>
            {step.label}
          </li>
        ))}
      </ol>
      <p className='text text-adriatic-500' role='status' aria-live='polite'>
        {message}
      </p>
    </div>
  )
}
