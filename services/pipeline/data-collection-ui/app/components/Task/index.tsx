import { useRef } from 'react'

import Container from '../Container'
import SelectTaskDialog from './SelectTaskDialog'
import type { Task } from './types'

type TaskProps = {
  activeTask: Task
  tasks: Task[]
  recordingState: string
}

export default function TaskComponent({ activeTask, tasks, recordingState }: TaskProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  return (
    <Container inline spacing='compact' title='Task'>
      <div className='w-full' />
      <span className='text shrink-0 leading-none'>{`"${activeTask.description}"`}</span>
      <div className='w-full' />
      <button
        onClick={() => dialogRef.current?.showModal()}
        className='action keyboard-focus h-full w-fit shrink-0 cursor-pointer rounded-sm px-2 py-1 disabled:text-adriatic-200 disabled:cursor-not-allowed'
        disabled={tasks.length < 2 || recordingState !== 'IDLE'}
      >
        Change task
      </button>
      <SelectTaskDialog dialogRef={dialogRef} tasks={tasks} activeTaskId={activeTask.task_id} />
    </Container>
  )
}
