import clsx from 'clsx'

type AnimatedRunningGirlProps = {
  inverted?: boolean
  className?: React.ComponentProps<'svg'>['className']
}

export default function AnimatedRunningGirl({ inverted = false, className }: AnimatedRunningGirlProps) {
  return (
    <svg
      style={{ '--pulse-speed': '0.8s' } as React.CSSProperties}
      className={clsx(inverted ? 'text-pastel-grey-100' : 'text-franka-blue-600', className)}
      width='141'
      height='161'
      viewBox='0 0 141 161'
      fill='none'
      xmlns='http://www.w3.org/2000/svg'
    >
      <defs>
        <linearGradient id='shimmer-gradient' gradientUnits='userSpaceOnUse' x1='-200' y1='0%' x2='0' y2='0%'>
          <stop offset='0%' stopColor='currentColor' stopOpacity='1' />
          <stop offset='50%' stopColor='currentColor' stopOpacity='0.3' />
          <stop offset='100%' stopColor='currentColor' stopOpacity='1' />
          <animateTransform
            attributeName='gradientTransform'
            type='translate'
            from='400 0'
            to='-400 0'
            dur='1.8s'
            repeatCount='indefinite'
          />
        </linearGradient>
      </defs>
      <g fill='url(#shimmer-gradient)'>
        <path d='M82.7874 38.5547L71.1902 15.2093L94.0328 2.90349L105.582 26.1776L82.7874 38.5547Z' />
        <path d='M51.4948 18.0268L37.2982 13.2973L60.3927 0.718994L74.5014 5.58275L51.4948 18.0268Z' />
        <path d='M126.289 61.5496L118.879 46.3029L140.494 53.8095L126.289 61.5496Z' />
        <path d='M71.6901 41.0703L56.9935 82.6292L109.981 53.9506L71.6901 41.0703Z' />
        <path d='M7.60516 93.195L0.506836 113.119L26.5607 99.357L7.60516 93.195Z' />
        <path d='M64.7917 88.365L27.9004 108.289L84.1871 127.408L64.7917 88.365Z' />
        <path d='M78.6444 133.89L71.5421 153.538L91.9613 160.98L78.6444 133.89Z' />
      </g>
    </svg>
  )
}
