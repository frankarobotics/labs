import { CircleQuestionMark } from 'lucide-react'

import Container from '@/components/Container'
import mapKnownDeviceToIcon from '@/utils/mapKnownDeviceToIcon'

import Device from './Device'
import type { DeviceStatus, DeviceStatusSeverity, DeviceType } from './types'

const STATUS_TO_SEVERITY: Record<DeviceStatus, DeviceStatusSeverity> = {
  UNKNOWN: 'unknown',
  ONLINE: 'positive',
  OFFLINE: 'negative',
  ERROR: 'negative',
}

type AcceptedKeys = 'robots' | 'cameras' | 'teleop'

type SystemStatusProps = {
  [x in AcceptedKeys]: Array<{
    name: string
    id: string
    type: DeviceType
    status: DeviceStatus
  }>
}

export default function SystemStatus({ cameras, teleop, robots }: SystemStatusProps) {
  return (
    <Container spacing='compact' title='System status'>
      <div className='screen:gap-9 flex flex-row gap-5'>
        {[['Teleoperation', teleop] as const, ['Cameras', cameras] as const, ['Robots', robots] as const].map(
          ([title, devices]) => (
            <div key={title} className='screen:gap-3 flex h-full w-full flex-col gap-2'>
              <span className='text font-bold'>{title}</span>
              <div className='grid h-full w-full grid-flow-row grid-cols-2 gap-2'>
                {devices.map((device) => (
                  <Device
                    Icon={mapKnownDeviceToIcon(device.id) ?? CircleQuestionMark}
                    key={device.name}
                    name={device.name}
                    status={STATUS_TO_SEVERITY[device.status]}
                  />
                ))}
              </div>
            </div>
          ),
        )}
      </div>
    </Container>
  )
}
