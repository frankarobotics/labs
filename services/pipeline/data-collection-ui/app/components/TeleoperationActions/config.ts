import {
  CircleStop,
  Focus,
  Link2,
  RefreshCw,
  RefreshCwOff,
  ThumbsDown,
  ThumbsUp,
  Trash2,
  Unlink2,
} from 'lucide-react'

import type { ButtonPlacement, ButtonSet } from './types'

export const KEYBOARD_CONFIG: Partial<Record<string, ButtonPlacement>> = {
  a: 'left',
  b: 'middle',
  c: 'right',
}

const IDLE_BUTTONS = {
  left: {
    label: 'Start teleoperation',
    Icon: Link2,
    disabled: false,
    type: 'primary',
    options: {
      action: '/api/teleop',
      method: 'post',
    },
    payload: {
      operation: 'start',
    },
  },
  middle: {
    label: 'Sync robots',
    Icon: RefreshCwOff,
    type: 'default',
    disabled: true,
  },
  right: {
    label: 'Start recording',
    Icon: Focus,
    type: 'default',
    disabled: true,
  },
} as const satisfies ButtonSet

const READY_BUTTONS = {
  left: {
    label: 'Stop teleoperation',
    Icon: Unlink2,
    type: 'negative',
    disabled: false,
    options: {
      action: '/api/teleop',
      method: 'post',
    },
    payload: {
      operation: 'stop',
    },
  },
  middle: {
    label: 'Sync robots',
    Icon: RefreshCw,
    type: 'primary',
    disabled: false,
    options: {
      action: '/api/follower-reset',
      method: 'post',
    },
    payload: {},
  },
  right: {
    label: 'Start recording',
    Icon: Focus,
    type: 'default',
    disabled: true,
  },
} as const satisfies ButtonSet

const SYNCING_BUTTONS = {
  left: {
    label: 'Stop teleoperation',
    Icon: Unlink2,
    type: 'negative',
    disabled: false,
    options: {
      action: '/api/teleop',
      method: 'post',
    },
    payload: {
      operation: 'stop',
    },
  },
  middle: {
    label: 'Syncing...',
    Icon: RefreshCw,
    type: 'primary',
    disabled: true,
  },
  right: {
    label: 'Start recording',
    Icon: Focus,
    type: 'default',
    disabled: true,
  },
} as const satisfies ButtonSet

const FOLLOWING_BUTTONS = {
  left: {
    label: 'Stop teleoperation',
    Icon: Unlink2,
    type: 'negative',
    disabled: false,
    options: {
      action: '/api/teleop',
      method: 'post',
    },
    payload: {
      operation: 'stop',
    },
  },
  middle: {
    label: 'Sync robots',
    Icon: RefreshCw,
    type: 'default',
    disabled: true,
  },
  right: {
    label: 'Start recording',
    Icon: Focus,
    type: 'primary',
    disabled: false,
    options: {
      action: '/api/record-start',
      method: 'post',
    },
    payload: {},
  },
} as const satisfies ButtonSet

const RECORDING_BUTTONS = {
  left: {
    label: 'Stop teleoperation',
    Icon: Unlink2,
    type: 'default',
    disabled: true,
  },
  middle: {
    label: 'Sync robots',
    Icon: RefreshCwOff,
    type: 'default',
    disabled: true,
  },
  right: {
    label: 'Stop recording',
    Icon: CircleStop,
    type: 'negative',
    disabled: false,
    options: {
      action: '/api/record-stop',
      method: 'post',
    },
    payload: {},
  },
} as const satisfies ButtonSet

const REVIEWING_BUTTONS = {
  left: {
    label: 'Discard',
    Icon: Trash2,
    type: 'negative',
    disabled: false,
    options: {
      action: '/api/review',
      method: 'post',
    },
    payload: {
      resolution: 'discarded',
    },
  },
  middle: {
    label: 'Save as failed',
    Icon: ThumbsDown,
    type: 'warning',
    disabled: false,
    options: {
      action: '/api/review',
      method: 'post',
    },
    payload: {
      resolution: 'rejected',
    },
  },
  right: {
    label: 'Save as successful',
    Icon: ThumbsUp,
    type: 'positive',
    disabled: false,
    options: {
      action: '/api/review',
      method: 'post',
    },
    payload: {
      resolution: 'accepted',
    },
  },
} as const satisfies ButtonSet

export function getButtonActions(workflowState: string, recordingState: string): ButtonSet {
  if (recordingState === 'RECORDING') return RECORDING_BUTTONS
  if (recordingState === 'REVIEWING') return REVIEWING_BUTTONS
  if (workflowState === 'FOLLOWING') return FOLLOWING_BUTTONS
  if (workflowState === 'SYNCING') return SYNCING_BUTTONS
  if (workflowState === 'READY') return READY_BUTTONS
  return IDLE_BUTTONS
}
