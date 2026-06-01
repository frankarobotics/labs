import clsx from 'clsx'
import React, {
  createContext,
  type PropsWithChildren,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'

export type ToastOptions = {
  duration?: number // ms; Infinity to pin
  important?: boolean // forces assertive announcement
}

type ToastAPI = {
  show: (message: React.ReactNode, opts?: ToastOptions) => void
  hide: () => void
}

const ToastContext = createContext<ToastAPI | null>(null)

export function useToast(): ToastAPI {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used inside <ToastProvider />')
  return ctx
}

type ProviderProps = PropsWithChildren<{
  defaultDuration?: number
  className?: string
}>

export function ToastProvider({ children, defaultDuration = 10000, className }: ProviderProps) {
  const popRef = useRef<HTMLDivElement | null>(null)
  const [content, setContent] = useState<React.ReactNode>(null)
  const [important, setImportant] = useState(false)

  // auto-dismiss bookkeeping
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const remainingRef = useRef<number>(defaultDuration)
  const startedAtRef = useRef(0)

  const clearTimer = () => {
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = null
  }

  const scheduleHide = useCallback((ms: number) => {
    clearTimer()
    if (!isFinite(ms)) return // pinned
    startedAtRef.current = performance.now()
    timerRef.current = setTimeout(() => popRef.current?.hidePopover(), ms)
  }, [])

  const hide = useCallback(() => popRef.current?.hidePopover(), [])

  const show = useCallback(
    (message: React.ReactNode, opts?: ToastOptions) => {
      setContent(message)
      setImportant(!!opts?.important)
      remainingRef.current = opts?.duration ?? defaultDuration

      const el = popRef.current
      if (!el) return

      // If already open, close then reopen next frame to replay transition
      if (el.matches(':popover-open')) {
        el.hidePopover()
        requestAnimationFrame(() => {
          el.showPopover()
          scheduleHide(remainingRef.current)
        })
      } else {
        el.showPopover()
        scheduleHide(remainingRef.current)
      }
    },
    [defaultDuration, scheduleHide],
  )

  // Pause on hover/focus; resume on leave/blur. Clear timer when closed.
  useEffect(() => {
    const el = popRef.current
    if (!el) return

    const pause = () => {
      if (!timerRef.current) return
      const elapsed = performance.now() - startedAtRef.current
      remainingRef.current = Math.max(0, remainingRef.current - elapsed)
      clearTimer()
    }
    const resume = () => {
      if (timerRef.current) return
      scheduleHide(remainingRef.current)
    }

    el.addEventListener('mouseenter', pause)
    el.addEventListener('mouseleave', resume)
    el.addEventListener('focusin', pause)
    el.addEventListener('focusout', resume)

    const onToggle = (e: Event) => {
      // @ts-expect-error ToggleEvent types land in newer TS lib
      if (e.newState === 'closed') clearTimer()
    }
    el.addEventListener('toggle', onToggle as EventListener)

    return () => {
      el.removeEventListener('mouseenter', pause)
      el.removeEventListener('mouseleave', resume)
      el.removeEventListener('focusin', pause)
      el.removeEventListener('focusout', resume)
      el.removeEventListener('toggle', onToggle as EventListener)
    }
  }, [scheduleHide])

  const api = useMemo<ToastAPI>(() => ({ show, hide }), [show, hide])

  return (
    <ToastContext.Provider value={api}>
      <style>{`
        @starting-style {
          [popover]:popover-open {
            transform: translateY(-100%);
          }
        }
      `}</style>

      {children}

      <div
        ref={popRef}
        popover='auto'
        role={important ? 'alert' : 'status'}
        aria-live={important ? 'assertive' : 'polite'}
        className={clsx(
          'text inset-auto -top-4 right-4 grid max-w-[min(92vw,420px)] grid-cols-[1fr_auto] gap-3 rounded-sm p-6 font-bold shadow-2xl',
          // closed state
          '-translate-y-full',
          // open state
          '[&:popover-open]:translate-y-8',
          // transitions (+ overlay/display discrete transitions in supporting engines)
          'transition-all duration-500 ease-out',
          'motion-reduce:transition-none',
          'bg-pastel-grey-200',
          className,
        )}
      >
        <div className='w-80'>{content}</div>
      </div>
    </ToastContext.Provider>
  )
}
