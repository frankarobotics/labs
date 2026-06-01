import { Outlet } from 'react-router'

import usePollLoader from '@/api/polling/usePollLoader'
import Container from '@/components/Container'
import Title from '@/components/Container/Title'
import secondsToMMSS from '@/utils/secondsToMMSS'
import unwrapOrThrow from '@/utils/unwrapOrThrow'

import type { Route } from './+types/index'
import EpisodeLink from './EpisodeLink'

export function meta() {
  return [{ title: 'Franka Data Collection -- Episodes' }, { name: 'description', content: 'View recorded episodes.' }]
}

export async function loader({ context: { DATA_COLLECTION_CLIENT: client } }: Route.LoaderArgs) {
  const episodes = await unwrapOrThrow(client.GET('/api/v1/episodes'))

  const filteredEpisodes = episodes
    .filter((episode) => episode.status === 'SAVED')
    .map(
      (episode) =>
        ({
          id: episode.episode_id,
          dateTimeIso: episode.created_at,
          duration: secondsToMMSS(episode.duration_seconds ?? 0),
          type:
            episode.label === 'REVIEW_SUCCESS' ? 'success' : episode.label === 'REVIEW_FAILED' ? 'failed' : 'unknown',
        }) as const,
    )
    .toSorted(({ dateTimeIso: a }, { dateTimeIso: b }) => {
      if ((a === null || a === undefined) && (b === null || b === undefined)) return NaN
      if (a === null || a === undefined) return +1
      if (b === null || b === undefined) return -1
      return new Date(b).getTime() - new Date(a).getTime()
    })

  return {
    episodes: filteredEpisodes,
  }
}

export default function Episodes({ loaderData: { episodes } }: Route.ComponentProps) {
  usePollLoader(1000)

  if (episodes.length === 0)
    return (
      <main className='mx-auto mt-20'>
        <Container spacing='wide'>
          <Title>{`No episode recorded yet!`}</Title>
          <p>{`Why don't you record something?`}</p>
        </Container>
      </main>
    )

  return (
    <main className='screen:gap-5 screen:p-5 grid h-full min-h-0 w-full grid-flow-row grid-cols-6 gap-3 p-3'>
      <div
        className='screen:-mb-5 relative col-span-2 -mb-3 h-full w-full overflow-hidden'
      >
        <div className='hidden-scrollbar screen:pb-30 col-span-2 flex h-full w-full flex-col gap-1 overflow-x-hidden overflow-y-auto pb-25 text-wrap'>
          {episodes.map((episode) => (
            <EpisodeLink key={episode.id} {...episode} />
          ))}
        </div>
        <div className='screen:h-30 pointer-events-none absolute right-0 bottom-0 left-0 h-25 w-full bg-gradient-to-b from-transparent to-white' />
      </div>
      <div className='col-span-4'>
        <Outlet />
      </div>
    </main>
  )
}
