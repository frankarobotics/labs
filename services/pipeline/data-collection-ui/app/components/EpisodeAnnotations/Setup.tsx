import { CircleCheck, CircleX, ExternalLink, KeyRound, LoaderCircle } from 'lucide-react'
import { useState } from 'react'
import { useFetcher } from 'react-router'

import type { StationAccount, StationSetup } from '@/api/annotations'

import { NOMADIC_BUTTON } from './nomadicButton'
import NomadicMark from './NomadicMark'

function Step({ number, title, children }: { number: number; title: string; children: React.ReactNode }) {
  return (
    <li className='grid grid-cols-[1.5rem_1fr] gap-3'>
      <span className='border-deep-sky text-deep-sky flex h-6 w-6 items-center justify-center rounded-full border-2 text-xs font-semibold'>
        {number}
      </span>
      <div className='flex flex-col gap-2'>
        <p className='text font-semibold'>{title}</p>
        {children}
      </div>
    </li>
  )
}

function ConnectForm({ endpoint }: { endpoint: string }) {
  const fetcher = useFetcher<{ account?: StationAccount; error?: string }>()
  const [apiKey, setApiKey] = useState('')
  const checking = fetcher.state !== 'idle'
  const { account, error } = checking ? {} : (fetcher.data ?? {})

  return (
    <fetcher.Form method='post' action={endpoint} className='flex flex-col gap-2'>
      <input type='hidden' name='intent' value='connect' />
      <div className='flex flex-wrap items-center gap-3'>
        <input
          type='password'
          name='api_key'
          aria-label='Nomadic API key'
          placeholder='Paste your Nomadic API key'
          autoComplete='off'
          spellCheck={false}
          value={apiKey}
          onChange={(event) => setApiKey(event.target.value)}
          disabled={checking}
          className='keyboard-focus border-pastel-grey-500 w-80 max-w-full rounded-[10px] border bg-white px-3 py-2 font-mono text-sm'
        />
        <button className={NOMADIC_BUTTON} type='submit' disabled={checking || !apiKey.trim()}>
          {checking ? (
            <LoaderCircle aria-hidden className='h-4 w-4 animate-spin' />
          ) : (
            <KeyRound aria-hidden className='h-4 w-4' />
          )}
          {checking ? 'Checking…' : 'Connect'}
        </button>
      </div>
      <p className='text min-h-5' role='status' aria-live='polite'>
        {checking && <span className='text-adriatic-500'>Checking the key with Nomadic…</span>}
        {account && (
          <span className='text-positive-600 inline-flex items-center gap-1.5'>
            <CircleCheck aria-hidden className='h-4 w-4' /> Key verified. Connected as {account.email ?? 'your account'}
            .
          </span>
        )}
        {error && (
          <span className='text-negative-600 inline-flex items-center gap-1.5'>
            <CircleX aria-hidden className='h-4 w-4' /> {error}
          </span>
        )}
      </p>
    </fetcher.Form>
  )
}

export default function Setup({ setup, endpoint }: { setup: StationSetup; endpoint: string }) {
  return (
    <div className='flex flex-col gap-4'>
      <p className='text max-w-[80ch]'>
        Connect this station to Nomadic to find timestamped robot actions in saved recordings.
      </p>
      <ol className='flex flex-col gap-5'>
        <Step number={1} title='Create a free Nomadic account'>
          <div className='flex flex-wrap items-center gap-3'>
            <a className={NOMADIC_BUTTON} href={setup.signup_url} target='_blank' rel='noreferrer'>
              <NomadicMark className='h-4 w-4' /> Create account
            </a>
            <a
              className='text keyboard-focus text-adriatic-500 inline-flex items-center gap-1 underline'
              href={setup.api_keys_url}
              target='_blank'
              rel='noreferrer'
            >
              I already have an account <ExternalLink aria-hidden className='h-3.5 w-3.5' />
            </a>
          </div>
        </Step>
        <Step number={2} title='Copy an API key'>
          <p className='text text-adriatic-500'>
            In Nomadic, open{' '}
            <a
              className='keyboard-focus inline-flex items-center gap-1 underline'
              href={setup.api_keys_url}
              target='_blank'
              rel='noreferrer'
            >
              Profile → API keys <ExternalLink aria-hidden className='h-3.5 w-3.5' />
            </a>
            , generate a key and copy it.
          </p>
        </Step>
        <Step number={3} title='Paste it here'>
          <ConnectForm endpoint={endpoint} />
        </Step>
      </ol>
      <p className='text text-adriatic-500 max-w-[80ch] text-xs'>
        The key is checked with Nomadic, saved in a key file on this station and never shown again. Once connected, only
        an administrator can change it, by removing the key file.
      </p>
    </div>
  )
}
