import Alert from '@/components/Alert'
import Container from '@/components/Container'
import Separator from '@/components/Container/Separator'

type RecordEpisodeProps = {
  workflowState: string
  recordingState: string
  duration?: string
}

function getLabel(state: string): string {
  return state.charAt(0).toUpperCase() + state.slice(1).toLowerCase()
}

function getAlert(workflowState: string, recordingState: string): string | null {
  if (recordingState === 'REVIEWING') return 'Recording ended. You can now save or discard the episode.'
  if (recordingState === 'RECORDING') return 'Recording in progress. You can stop recording at any time.'
  if (workflowState === 'IDLE') return 'Start teleoperation and sync the robots.'
  if (workflowState === 'SYNCING') return 'Syncing in progress. Please wait...'
  if (workflowState === 'READY') return 'Sync the robots to start recording.'
  if (workflowState === 'FOLLOWING') return 'Ready to record.'
  if (workflowState === 'AUTORECOVERY') return 'Attempting auto-recovery after controller error. Please wait...'
  return null
}

export default function RecordEpisode({ workflowState, recordingState, duration }: RecordEpisodeProps) {
  const alert = getAlert(workflowState, recordingState)

  return (
    <Container spacing='compact' title='Record episode'>
      <Separator />
      <div className='fullbleed padding flex flex-row justify-between'>
        <span className='text text-franka-blue-200'>Workflow</span>
        <span className='text'>{getLabel(workflowState)}</span>
      </div>
      <Separator />
      <div className='fullbleed padding flex flex-row justify-between'>
        <span className='text text-franka-blue-200'>Recording</span>
        <span className='text'>
          {getLabel(recordingState)}
          {recordingState !== 'IDLE' && duration && ` (${duration} min)`}
        </span>
      </div>
      {alert && (
        <>
          <Separator />
          <Alert>{alert}</Alert>
        </>
      )}
    </Container>
  )
}
