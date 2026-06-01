import type { SubmitOptions } from 'react-router'

type ButtonSeverity = 'primary' | 'positive' | 'warning' | 'negative' | 'default'

type ButtonSpec = {
  label: string
  Icon: React.FunctionComponent<React.SVGProps<SVGSVGElement>>
  type: ButtonSeverity
} & (
  | {
      disabled: true
    }
  | {
      label: string
      Icon: React.FunctionComponent<React.SVGProps<SVGSVGElement>>
      disabled: false
      options: SubmitOptions
      payload: { [x in string]: unknown }
    }
)

type ButtonPlacement = 'left' | 'middle' | 'right'

type ButtonSet = {
  [x in ButtonPlacement]: ButtonSpec
}
