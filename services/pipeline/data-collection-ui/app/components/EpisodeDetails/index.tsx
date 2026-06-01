type EpisodeDetailsKeys = 'date' | 'time' | 'duration' | 'type'
type EpisodeDetailsProps = {
  [x in EpisodeDetailsKeys]: string
} & {
  taskDescription?: string | null
}

export default function EpisodeDetails({ date, time, duration, type, taskDescription }: EpisodeDetailsProps) {
  return (
    <div className='grid w-full grid-flow-row grid-cols-4 gap-y-(--container-spacing)'>
      <div className='screen:gap-2 flex flex-col items-start justify-start gap-1'>
        <span suppressHydrationWarning className='text'>
          {date}
        </span>
        <span className='text text-franka-blue-200'>Date</span>
      </div>
      <div className='screen:gap-2 flex flex-col items-start justify-start gap-1'>
        <span suppressHydrationWarning className='text'>
          {time}
        </span>
        <span className='text text-franka-blue-200'>Time</span>
      </div>
      <div className='screen:gap-2 flex flex-col items-start justify-start gap-1'>
        <span className='text'>{duration} min</span>
        <span className='text text-franka-blue-200'>Duration</span>
      </div>
      <div className='screen:gap-2 flex flex-col items-start justify-start gap-1'>
        <span className='text'>{type}</span>
        <span className='text text-franka-blue-200'>Type</span>
      </div>
      {taskDescription && (
        <div className='screen:gap-2 col-span-2 flex flex-col items-start justify-start gap-1'>
          <span className='text'>{taskDescription}</span>
          <span className='text text-franka-blue-200'>Task</span>
        </div>
      )}
    </div>
  )
}
