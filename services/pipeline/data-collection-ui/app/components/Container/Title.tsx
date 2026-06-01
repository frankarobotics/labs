import clsx from 'clsx'

export default function Title({
  children,
  className,
}: {
  children: React.ReactNode
  className?: React.ComponentProps<'h3'>['className']
}) {
  return <h3 className={clsx('header', className)}>{children}</h3>
}
