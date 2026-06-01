import clsx from 'clsx'

type DeviceProps = {
  name: string
  Icon: React.FunctionComponent<React.SVGProps<SVGSVGElement>>
  status: 'negative' | 'positive' | 'unknown'
}

export default function Device({ name, Icon, status }: DeviceProps) {
  return (
    <article
      className={clsx(
        'screen:py-3 screen:px-5 screen:h-11 flex h-8 flex-row items-center gap-2 overflow-hidden rounded-sm border-solid px-3 py-2',
        status === 'negative' && 'bg-negative justify-between',
        status === 'positive' && 'bg-pastel-grey-200 border-positive justify-start border-r-8',
        status === 'unknown' && 'bg-pastel-grey-200 border-adriatic justify-start border-r-8',
      )}
    >
      {status !== 'negative' && (
        <Icon className='screen:h-5 screen:w-5 stroke-franka-blue-600 h-4 w-4 shrink-0 fill-none' />
      )}
      <span className='text overflow-hidden leading-none text-ellipsis'>{name}</span>
    </article>
  )
}
