import { LoaderCircle } from 'lucide-react'
import { useEffect } from 'react'
import { data } from 'react-router'

import usePollLoader from '@/api/polling/usePollLoader'
import Container from '@/components/Container'
import RecordEpisode from '@/components/RecordEpisode'
import SystemStatus from '@/components/SystemStatus'
import Task from '@/components/Task'
import TeleoperationActions from '@/components/TeleoperationActions'
import { useToast } from '@/components/Toasts'
import { WebsocketCanvas } from '@/components/WebsocketCanvas/WebsocketCanvas'
import { CookieScope } from '@/sessions/CookieScope'
import { getTask, verifyTask } from '@/sessions/task'
import compareDeviceDirectionNames from '@/utils/compareDeviceDirectionNames'
import mapKnownDeviceName from '@/utils/mapKnownDeviceNames'
import secondsToMMSS from '@/utils/secondsToMMSS'
import snakeCaseToTitleCase from '@/utils/snakeCaseToTitleCase'
import unwrapOrThrow from '@/utils/unwrapOrThrow'

import type { Route } from './+types/index'

export function meta() {
  return [{ title: 'Franka Data Collection' }, { name: 'description', content: 'Record teleoperation data' }]
}

export async function loader({
  request,
  context: { DATA_COLLECTION_CLIENT: client, DATA_COLLECTION_URL: url },
}: Route.LoaderArgs) {
  const cookieScope = new CookieScope(request)
  // verify if the task cookie is correct
  // currently hard-coded
  await verifyTask(cookieScope, client)
  const systemInfo = await unwrapOrThrow(client.GET('/api/v1/system/info'))
  const activeEpisodeId = systemInfo.active_episode?.id

  const task_id = await getTask(cookieScope)

  const devices = await unwrapOrThrow(client.GET('/api/v1/devices'))

  const tasks = await unwrapOrThrow(client.GET('/api/v1/tasks'))

  const cameras = devices
    .filter((device) => device.type.includes('CAMERA'))
    .map((device) => ({
      name: mapKnownDeviceName(device.id) ?? snakeCaseToTitleCase(device.id),
      id: device.id,
      status: device.status,
      type: device.type as 'ZED_CAMERA' | 'REALSENSE_CAMERA',
      wsUrl: `${url.href}api/v1/ws/cameras/${device.id}`,
    }))
    .toSorted((a, b) => compareDeviceDirectionNames(a.id, b.id))

  const teleop = devices
    .filter((device) => device.type === 'TELEOP_ROBOT')
    .map((device) => ({
      name: mapKnownDeviceName(device.id) ?? snakeCaseToTitleCase(device.id),
      id: device.id,
      status: device.status,
      type: device.type,
    }))
    .toSorted((a, b) => compareDeviceDirectionNames(a.id, b.id))

  const robots = devices
    .filter((device) => device.type === 'ROBOT_OBSERVER')
    .map((device) => ({
      name: mapKnownDeviceName(device.id) ?? snakeCaseToTitleCase(device.id),
      id: device.id,
      status: device.status,
      type: device.type,
    }))
    .toSorted((a, b) => compareDeviceDirectionNames(a.id, b.id))

  const workflowState = systemInfo.workflow_state
  const recordingState = systemInfo.recording_state

  let duration: string | undefined

  if (activeEpisodeId) {
    const { data: episodeData } = await client.GET('/api/v1/episodes/{episode_id}', {
      params: { path: { episode_id: activeEpisodeId } },
    })

    if (recordingState === 'RECORDING') {
      if (episodeData && typeof episodeData.created_at === 'string') {
        duration = secondsToMMSS((Date.now() - new Date(episodeData.created_at).getTime()) / 1000)
      }
    }
    if (recordingState === 'REVIEWING') {
      if (episodeData && typeof episodeData.duration_seconds === 'number') {
        duration = secondsToMMSS(episodeData.duration_seconds)
      }
    }
  }

  return data(
    {
      workflowState,
      recordingState,
      duration,
      cameras,
      robots,
      teleop,
      tasks,
      activeTask: tasks.find((task) => task.task_id === task_id)!,
    },
    {
      headers: cookieScope.headers,
    },
  )
}

export default function Home({
  loaderData: { workflowState, recordingState, duration, cameras, robots, teleop, tasks, activeTask },
}: Route.ComponentProps) {
  usePollLoader()
  const toast = useToast()

  useEffect(() => {
    if (workflowState === 'AUTORECOVERY') {
      toast.show(
        <div className='flex flex-row items-center gap-3'>
          <LoaderCircle className='h-5 w-5 shrink-0 animate-spin' />
          <span>Attempting auto-recovery after controller error. Please wait...</span>
        </div>,
        { duration: Infinity, important: true, variant: 'error' },
      )
    } else {
      toast.hide()
    }
  }, [workflowState, toast])

  return (
    <main className='screen:gap-5 screen:p-5 flex h-full min-h-0 w-full flex-col gap-3 p-3'>
      <div className='grid grid-cols-6 gap-3'>
        <div className='col-span-2'>
          <RecordEpisode workflowState={workflowState} recordingState={recordingState} duration={duration} />
        </div>
        <div className='col-span-4'>
          <SystemStatus teleop={teleop} cameras={cameras} robots={robots} />
        </div>
      </div>
      <div className='screen:gap-6 bg-pastel-grey-100 screen:p-5 flex w-full flex-row justify-around gap-3 overflow-auto rounded-sm p-3'>
        {cameras.map(({ name, wsUrl, status }) => (
          <WebsocketCanvas key={wsUrl} status={status} name={name} url={wsUrl} />
        ))}
      </div>
      <Task tasks={tasks} activeTask={activeTask} recordingState={recordingState} />
      <Container className='shrink-0' spacing='compact' title='Controls'>
        <div className='flex w-full shrink-0 flex-row gap-9'>
          <TeleoperationActions workflowState={workflowState} recordingState={recordingState} />
        </div>
      </Container>
    </main>
  )
}
