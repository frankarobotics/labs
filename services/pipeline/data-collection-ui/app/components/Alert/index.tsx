import { Info } from 'lucide-react'

export default function Alert({ children }: { children: React.ReactNode }) {
  return (
    <div className='flex flex-row items-center justify-start gap-2'>
      <Info className='stroke-franka-blue-600 h-6 w-6' />
      <span className='text max-w-[80ch]'>{children}</span>
    </div>
  )
}
