import clsx from 'clsx'
import { type NavLinkProps } from 'react-router'
import { NavLink } from 'react-router'

import FrankaLogo from './running_girl.svg?react'

type FrankaLinkProps = Omit<NavLinkProps, 'className'>

export function FrankaLink({ children, ...props }: FrankaLinkProps) {
  return (
    <NavLink
      {...props}
      className={({ isActive, isPending, isTransitioning }) =>
        clsx(
          'h-fit text-base leading-none font-bold',
          isActive && 'text-white',
          !isActive && !(isPending || isTransitioning) && 'text-adriatic-300',
          (isPending || isTransitioning) && 'from-adriatic-300 to-adriatic-300 shimmer-text bg-linear-to-r via-white',
        )
      }
    >
      {children}
    </NavLink>
  )
}

export default function Header() {
  return (
    <header className='bg-franka-blue-600 flex w-full flex-row items-center justify-start gap-10 py-6 ps-10 select-none'>
      <FrankaLogo className='h-8 w-8 fill-white' />
      <FrankaLink to='/collect'>COLLECT DATA</FrankaLink>
      <FrankaLink to='/episodes'>EPISODES</FrankaLink>
    </header>
  )
}
