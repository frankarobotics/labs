import clsx from 'clsx'
import { X } from 'lucide-react'
import { useFetcher } from 'react-router'

import Container from '../Container'
import type { Task } from './types'

type SelectTaskDialogProps = {
  activeTaskId: string
  tasks: Task[]
  dialogRef?: React.RefObject<HTMLDialogElement | null>
}

export default function SelectTaskDialog({ activeTaskId, tasks, dialogRef }: SelectTaskDialogProps) {
  const fetcher = useFetcher()
  return (
    <dialog className='sidebar-menu' ref={dialogRef}>
      <Container spacing='compact' title='Change task'>
        <button
          aria-label='close'
          onClick={() => dialogRef?.current?.close()}
          className='fullbleed-t fullbleed-r keyboard-focus absolute cursor-pointer rounded-sm'
        >
          <X className='stroke-franka-blue-600 h-6 w-6' />
        </button>
        <fetcher.Form
          className='screen:gap-3 flex flex-col content-start items-start gap-2'
          method='post'
          action='/api/task'
          onSubmit={() => dialogRef?.current?.close()}
        >
          {tasks.map(({ task_id, name, description }) => (
            <button
              className={clsx(
                'keyboard-focus flex w-full cursor-pointer flex-col content-start items-start rounded-sm border-l-6 border-solid p-4 pl-[18px] text-left transition-colors',
                !(task_id === activeTaskId) && 'border-pastel-grey-100 bg-pastel-grey-100 hover:bg-transparent',
                task_id === activeTaskId && 'border-deep-sky bg-transparent',
              )}
              key={task_id}
              type='submit'
              name='task'
              value={task_id}
            >
              <span className='header'>{name}</span>
              <span className='text'>{description}</span>
            </button>
          ))}
        </fetcher.Form>
      </Container>
    </dialog>
  )
}
