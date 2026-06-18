import { redirect } from 'react-router'

import usePollLoader from '@/api/polling/usePollLoader'
import Container from '@/components/Container'
import Separator from '@/components/Container/Separator'
import ContainerTitle from '@/components/Container/Title'
import EpisodeActions from '@/components/EpisodeActions'
import EpisodeDetails from '@/components/EpisodeDetails'
import { WebsocketCanvas } from '@/components/WebsocketCanvas/WebsocketCanvas'
import compareDeviceDirectionNames from '@/utils/compareDeviceDirectionNames'
import secondsToMMSS from '@/utils/secondsToMMSS'
import snakeCaseToTitleCase from '@/utils/snakeCaseToTitleCase'
import unwrapOrThrow from '@/utils/unwrapOrThrow'
import useLocalizedDateTime from '@/utils/useLocalizedDateTime'

import type { Route } from './+types/index'

export async function loader({
  params: { episode_id },
  context: { DATA_COLLECTION_CLIENT: client, DATA_COLLECTION_URL: url },
}: Route.LoaderArgs) {
  const episode = await unwrapOrThrow(
    client.GET('/api/v1/episodes/{episode_id}', {
      params: { path: { episode_id } },
    }),
    {
      onHttpError: (res) => {
        if (res.response.status === 404) throw redirect('../')
      },
    },
  )

  const task = await unwrapOrThrow(
    client.GET('/api/v1/tasks/{task_id}', {
      params: { path: { task_id: episode.task_id } },
    }),
  )

  const devices = await unwrapOrThrow(client.GET('/api/v1/devices'))

  const cameras = devices
    .filter((device) => device.type.includes('CAMERA'))
    .map((device) => ({
      name: snakeCaseToTitleCase(device.id),
      id: device.id,
      status: device.status,
      type: device.type as 'ZED_CAMERA' | 'REALSENSE_CAMERA',
      wsUrl: `${url.href}api/v1/ws/cameras/${device.id}`,
    }))
    .toSorted((a, b) => compareDeviceDirectionNames(a.id, b.id))

  return {
    episode: {
      id: episode.episode_id,
      dateTimeIso: episode.created_at,
      duration: secondsToMMSS(episode.duration_seconds ?? 0),
      type: (episode.label ?? 'UNKNOWN').toLowerCase(),
      taskDescription: task.description,
    },
    cameras,
  }
}

export default function Episode({
  loaderData: {
    episode: { id, dateTimeIso, duration, type, taskDescription },
    cameras,
  },
}: Route.ComponentProps) {
  usePollLoader()
  const { date, time } = useLocalizedDateTime(dateTimeIso)

  return (
    <Container spacing='wide' className='static'>
      <ContainerTitle>{`Episode ${id}`}</ContainerTitle>
      <EpisodeDetails date={date} time={time} duration={duration} type={type} taskDescription={taskDescription} />
      <Separator />
      <div className='screen:gap-6 bg-pastel-grey-100 flex w-full flex-row justify-around gap-3 overflow-auto rounded-sm'>
        {cameras.map(({ name, wsUrl, status }) => (
          <WebsocketCanvas key={wsUrl} status={status} name={name} url={wsUrl} />
        ))}
      </div>
      <Separator />
      <ContainerTitle>Actions</ContainerTitle>
      <EpisodeActions id={id} />
    </Container>
  )
}
