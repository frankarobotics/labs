import clsx from 'clsx'

import Title from './Title'

type ContainerProps = {
  className?: React.HTMLAttributes<HTMLElement>['className']
  spacing: 'wide' | 'compact'
  inline?: boolean
  title?: string
  children: React.ReactNode
}

export default function Container({ spacing, inline = false, title, children, className }: ContainerProps) {
  return (
    <section data-spacing={spacing} className={clsx('section-container', inline && 'flex-row items-center', className)}>
      {title && <Title>{title}</Title>}
      {children}
    </section>
  )
}
