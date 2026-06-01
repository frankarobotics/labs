import clsx from 'clsx'

import type { ButtonPlacement } from './types'

type TeleoperationButtonProps = {
  label: string
  Icon: React.FunctionComponent<React.SVGProps<SVGSVGElement>>
  placement: ButtonPlacement
  type: 'primary' | 'positive' | 'warning' | 'negative' | 'default'
  onClick: () => void
  disabled?: boolean
  ref: React.Ref<HTMLButtonElement>
}

const placementToLabel = {
  left: 'L',
  middle: 'M',
  right: 'R',
} satisfies Record<ButtonPlacement, string>

export default function TeleoperationButton({
  label,
  onClick,
  Icon,
  placement,
  type,
  disabled,
  ref,
}: TeleoperationButtonProps) {
  return (
    <div className='flex w-full flex-col items-center justify-center gap-4'>
      <button
        ref={ref}
        type='button'
        disabled={disabled}
        onClick={onClick}
        className={clsx(
          'keyboard-focus group disabled:bg-pastel-grey-300 shadow-adriatic/30 relative mb-9 flex h-15 w-full cursor-pointer flex-row items-center justify-center rounded-sm shadow-md transition duration-500 active:shadow-sm disabled:cursor-not-allowed disabled:shadow-none',
          type === 'default' && 'bg-pastel-grey-300',
          type === 'warning' &&
            'bg-critical-lemon hover:active:bg-critical-lemon hover:bg-critical-lemon/60 ring-critical-lemon/30 active:ring-critical-lemon/60',
          type === 'primary' &&
            'bg-deep-sky hover:active:bg-deep-sky hover:bg-deep-sky/60 ring-deep-sky/30 active:ring-deep-sky/60',
          type === 'positive' &&
            'bg-positive hover:active:bg-positive hover:bg-positive/60 ring-positive/30 active:ring-positive/60',
          type === 'negative' &&
            'bg-negative hover:active:bg-negative hover:bg-negative/60 ring-negative/30 active:ring-negative/60',
        )}
      >
        <span
          className={clsx(
            'text-franka-blue-600 group-disabled:adriatic-200 absolute inset-y-0 left-3 my-auto h-fit transition-colors duration-500',
          )}
        >
          {placementToLabel[placement]}
        </span>
        <Icon
          className={clsx(
            'stroke-deep-sky group-disabled:stroke-adriatic-200 screen:h-9 screen:w-9 h-6 w-6 fill-none transition-colors duration-500',
            type === 'default' && 'stroke-deep-sky',
            type !== 'default' && 'stroke-franka-blue-600',
          )}
        />
        <span
          className={clsx(
            // 'text-franka-blue-600 group-disabled:text-adriatic-200 pointer-events-none absolute -bottom-9 text-sm font-medium transition-colors duration-500',
            'text pointer-events-none absolute -bottom-9 transition-colors duration-500',
          )}
        >
          {label}
        </span>
      </button>
    </div>
  )
}
