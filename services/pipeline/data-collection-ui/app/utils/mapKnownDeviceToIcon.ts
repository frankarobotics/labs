import { Brackets, Gamepad2, Rotate3d, Video } from 'lucide-react'

export default function mapKnownDeviceToIcon(id: string) {
  switch (id) {
    case 'left_arm':
    case 'right_arm':
      return Gamepad2
    case 'left_gripper':
    case 'right_gripper':
      return Brackets
    case 'franka_robot_left':
    case 'franka_robot_right':
      return Rotate3d
    case 'head_camera':
    case 'wrist_camera_left':
    case 'wrist_camera_right':
      return Video
    default:
      return null
  }
}
