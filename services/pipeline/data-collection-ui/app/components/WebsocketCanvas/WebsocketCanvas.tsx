import { useRef } from 'react'

import type { DeviceStatus } from '../SystemStatus/types'
import { useWebSocketCanvas } from './useWebsocketCanvas'

export function WebsocketCanvas({ name, url, status }: { name: string; url: string; status: DeviceStatus }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  useWebSocketCanvas({ url, canvasRef })

  return (
    <div className='relative flex w-full flex-col items-center gap-3'>
      <span className='text font-bold'>{name}</span>
      <canvas className='aspect-4/3 h-auto w-full overflow-hidden rounded-sm' ref={canvasRef} />
      {status !== 'ONLINE' && (
        <span className='text bg-negative-600 absolute bottom-2 h-fit w-fit rounded-full px-4 py-2 leading-none font-bold text-white'>
          CAMERA OFFLINE
        </span>
      )}
    </div>
  )
}
