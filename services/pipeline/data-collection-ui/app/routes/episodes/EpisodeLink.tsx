import clsx from 'clsx'
import { NavLink } from 'react-router'

import useLocalizedDateTime from '@/utils/useLocalizedDateTime'

type EpisodeLinkProps = {
  id: string
  dateTimeIso: string | null | undefined
  duration: string
  type: 'success' | 'failed' | 'unknown'
}

export default function EpisodeLink({ id, dateTimeIso, duration, type }: EpisodeLinkProps) {
  const { date, time } = useLocalizedDateTime(dateTimeIso)

  return (
    <NavLink
      to={`./${id}`}
      className={({ isActive }) =>
        clsx(
          'screen:gap-5 screen:p-5 screen:pl-6 flex flex-col items-start justify-start gap-3 rounded-sm border-l-6 border-solid p-3 pl-[18px]',
          !isActive && 'border-pastel-grey-100 bg-pastel-grey-100',
          isActive && 'border-deep-sky bg-none',
        )
      }
    >
      <span className='header font-mono text-xs'>{id}</span>
      <div className='grid w-full grid-flow-row grid-cols-4'>
        <span suppressHydrationWarning className='text'>
          {date}
        </span>
        <span suppressHydrationWarning className='text text-left'>
          {time}
        </span>
        <span className='text col-span-1 text-right'>{duration} min</span>
        <span
          className={clsx(
            'text col-span-1 text-right',
            type === 'success' && 'text-positive-600',
            type === 'failed' && 'text-negative-600',
          )}
        >
          {type}
        </span>
      </div>
    </NavLink>
  )
}
