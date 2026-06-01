import { useEffect, useRef, useState } from 'react'
import { useFetcher } from 'react-router'

import { useToast } from '@/components/Toasts'

import { getButtonActions, KEYBOARD_CONFIG } from './config'
import TeleoperationButton from './TeleoperationButton'
import type { ButtonPlacement } from './types'
import useReviewFeedback from './useReviewFeedback'

type TeleoperationActionsProps = {
  workflowState: string
  recordingState: string
}

const buttonOrder: ButtonPlacement[] = ['left', 'middle', 'right'] as const

export default function TeleoperationActions({ workflowState, recordingState }: TeleoperationActionsProps) {
  const fetcher = useFetcher()
  const toast = useToast()
  useReviewFeedback(fetcher)
  const isBusy = fetcher.state !== 'idle'

  const [stableWorkflow, setStableWorkflow] = useState(workflowState)
  const [stableRecording, setStableRecording] = useState(recordingState)

  const htmlButtonsRef = useRef<{
    [Key in ButtonPlacement]: HTMLButtonElement | null
  }>({
    left: null,
    middle: null,
    right: null,
  })

  useEffect(() => {
    if (!isBusy) {
      setStableWorkflow(workflowState)
      setStableRecording(recordingState)
    }
  }, [isBusy, workflowState, recordingState])

  const currentButtons = getButtonActions(stableWorkflow, stableRecording)
  const buttonConfigRef = useRef(currentButtons)

  useEffect(() => {
    buttonConfigRef.current = currentButtons
  }, [currentButtons])

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      // no modifiers
      if (e.repeat || e.altKey || e.ctrlKey || e.metaKey) return
      const t = e.target as HTMLElement | null
      // no text entry
      if (t?.tagName === 'INPUT' || t?.tagName === 'TEXTAREA') return
      const ce = t?.getAttribute('contenteditable')
      if (ce !== null && ce !== undefined && ce.toLowerCase() !== 'false') return
      // do not fire if previous request isn't done
      if (fetcher.state !== 'idle') return

      const buttonPlacement = KEYBOARD_CONFIG[e.key.toLowerCase()]
      if (!buttonPlacement) return
      const action = buttonConfigRef.current[buttonPlacement]
      if (!action || action.disabled || !action.options) return
      e.preventDefault()
      toast.show(
        <div className='flex flex-col gap-1'>
          <span className='leading-none'>{action.label}</span>
          <span className='text-franka-blue-200/90 leading-none font-normal'>Pressed {buttonPlacement} foot pedal</span>
        </div>,
        { duration: 1000 },
      )
      fetcher.submit(action.payload, action.options)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [fetcher, toast])

  return buttonOrder.map((place) => {
    const action = currentButtons[place]

    return (
      <TeleoperationButton
        ref={(el) => {
          htmlButtonsRef.current[place] = el
        }}
        key={place}
        Icon={action.Icon}
        placement={place}
        type={action.type}
        disabled={action.disabled || fetcher.state !== 'idle'}
        onClick={() => {
          if (action.disabled) return
          if (fetcher.state !== 'idle') return
          fetcher.submit(action.payload, action.options)
        }}
        label={action.label}
      />
    )
  })
}
