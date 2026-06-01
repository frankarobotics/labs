const DEVICE_ORDER = ['camera', 'arm', 'gripper', 'robot'] as const
const DIRECTION_ORDER = ['frame', 'left', 'middle', 'head', 'right']

function deviceRank(name: string): number {
  const lower = name.toLowerCase()
  const i = DEVICE_ORDER.findIndex((d) => lower.includes(d))
  return i === -1 ? Number.POSITIVE_INFINITY : i
}

function directionRank(name: string): number {
  const lower = name.toLowerCase()
  const i = DIRECTION_ORDER.findIndex((d) => lower.includes(d))
  return i === -1 ? Number.POSITIVE_INFINITY : i
}

export default function compareDeviceDirectionNames(a: string, b: string): number {
  const ad = deviceRank(a),
    bd = deviceRank(b)
  if (ad !== bd) return ad - bd

  const ar = directionRank(a),
    br = directionRank(b)
  if (ar !== br) return ar - br

  return a.localeCompare(b, undefined, { sensitivity: 'base' })
}
