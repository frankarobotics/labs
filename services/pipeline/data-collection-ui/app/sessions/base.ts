import type { CookieOptions } from 'react-router'

const base: CookieOptions = {
  httpOnly: true,
  sameSite: 'lax',
  path: '/',
  secure: false,
}

export default base
