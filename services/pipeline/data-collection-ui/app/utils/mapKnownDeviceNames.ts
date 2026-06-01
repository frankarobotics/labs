const KNOWN_DEVICE_NAMES: Record<string, string> = {
  left_arm: 'Arm Left',
  left_gripper: 'Gripper Left',
  right_arm: 'Arm Right',
  right_gripper: 'Gripper Right',
  head_camera: 'Camera Head',
  wrist_camera_left: 'Camera Left Wrist',
  wrist_camera_right: 'Camera Right Wrist',
  franka_robot_left: 'FR3 Left',
  franka_robot_right: 'FR3 Right',
} as const

export default function mapKnownDeviceName(name: string): string | undefined {
  return KNOWN_DEVICE_NAMES[name]
}
