import clsx from 'clsx'

type Variant = 'primary' | 'negative' | 'outline'

type ButtonProps = Omit<React.ComponentProps<'button'>, 'className'> & {
  variant: Variant
}

type ButtonLinkProps = Omit<React.ComponentProps<'a'>, 'className'> & {
  variant: Variant
}

function buttonClassName(variant: Variant) {
  return clsx(
    'keyboard-focus screen:px-5 text screen:py-3 screen:gap-3 flex flex-row items-center justify-start gap-2 rounded-sm px-3 py-2 transition duration-300 active:ring-4',
    variant === 'negative' &&
      'bg-negative hover:active:bg-negative hover:bg-negative/60 ring-negative/30 active:ring-negative/60',
    variant === 'primary' &&
      'bg-deep-sky hover:active:bg-deep-sky hover:bg-deep-sky/60 ring-deep-sky/30 active:ring-deep-sky/60',
    variant === 'outline' &&
      'hover:active:bg-deep-sky-100 hover:bg-deep-sky-100/60 border-deep-sky ring-deep-sky/30 active:ring-deep-sky/60 border-1 bg-transparent',
  )
}

export default function Button({ variant, ...props }: ButtonProps) {
  return <button {...props} className={buttonClassName(variant)}></button>
}

// A link that looks like a button, for downloads and pages in a new tab
export function ButtonLink({ variant, ...props }: ButtonLinkProps) {
  return <a {...props} className={buttonClassName(variant)}></a>
}
