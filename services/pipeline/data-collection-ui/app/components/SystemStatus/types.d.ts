import paths from '@/api/data-collection/types'

type DeviceStatus = paths.components['schemas']['DeviceStatus']
type DeviceType = paths.components['schemas']['DeviceType']

type DeviceStatusSeverity = 'positive' | 'negative' | 'unknown'
