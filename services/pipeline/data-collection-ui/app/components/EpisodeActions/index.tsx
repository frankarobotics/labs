import { Trash2 } from 'lucide-react'
import { useRef } from 'react'

import Button from '../Button'
import DeleteEpisodeDialog from './DeleteEpisodeDialog'

export default function EpisodeActions({ id }: { id: string }) {
  const deleteDialogRef = useRef<HTMLDialogElement>(null)
  return (
    <div className='flex flex-row items-center justify-between'>
      <Button variant='negative' type='button' onClick={() => deleteDialogRef.current?.showModal()}>
        <Trash2 className='stroke-franka-blue-600 h-4 w-4 fill-none' />
        Delete episode
      </Button>
      <DeleteEpisodeDialog ref={deleteDialogRef} id={id} />
    </div>
  )
}
