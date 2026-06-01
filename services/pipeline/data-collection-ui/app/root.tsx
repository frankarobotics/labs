import '@/app.css'

import { isRouteErrorResponse, Links, Meta, Outlet, Scripts, ScrollRestoration } from 'react-router'

import usePollLoader from '@/api/polling/usePollLoader'
import AnimatedRunningGirl from '@/components/AnimatedRunningGirl'
import Container from '@/components/Container'
import Title from '@/components/Container/Title'
import Header from '@/components/Header'
import { ToastProvider } from '@/components/Toasts'
import fontStyles from '@/styles/fonts.css?url'

import type { Route } from './+types/root'

export const links: Route.LinksFunction = () => [
  { rel: 'icon', type: 'image/png', href: '/favicon-96x96.png', sizes: '96x96' },
  { rel: 'icon', type: 'image/svg+xml', href: '/favicon.svg' },
  { rel: 'shortcut icon', href: '/favicon.ico' },
  { rel: 'apple-touch-icon', sizes: '180x180', href: '/apple-touch-icon.png' },
  { rel: 'manifest', href: '/site.webmanifest' },
  {
    rel: 'preload',
    href: '/fonts/Lato-Regular.woff2',
    as: 'font',
    type: 'font/woff2',
    crossOrigin: 'anonymous',
  },
  {
    rel: 'preload',
    href: '/fonts/Lato-Italic.woff2',
    as: 'font',
    type: 'font/woff2',
    crossOrigin: 'anonymous',
  },
  {
    rel: 'preload',
    href: '/fonts/Lato-Bold.woff2',
    as: 'font',
    type: 'font/woff2',
    crossOrigin: 'anonymous',
  },
  {
    rel: 'preload',
    href: '/fonts/Lato-BoldItalic.woff2',
    as: 'font',
    type: 'font/woff2',
    crossOrigin: 'anonymous',
  },
  {
    rel: 'stylesheet',
    href: fontStyles,
    type: 'text/css',
  },
]

export function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html lang='en'>
      <head>
        <meta charSet='utf-8' />
        <meta name='viewport' content='width=device-width, initial-scale=1' />
        <meta name='apple-mobile-web-app-title' content='LABS' />
        <Meta />
        <Links />
      </head>
      <body className='flex h-screen flex-col items-start justify-start overflow-hidden'>
        <Header />
        <ToastProvider>{children}</ToastProvider>
        <ScrollRestoration />
        <Scripts />
      </body>
    </html>
  )
}

export default function App() {
  return <Outlet />
}

export function ErrorBoundary({ error }: Route.ErrorBoundaryProps) {
  const isBooting =
    isRouteErrorResponse(error) &&
    error.status === 503 &&
    error.data &&
    typeof error.data === 'object' &&
    'code' in error.data &&
    (error.data.code === 'ECONNREFUSED' || error.data.code === 'UND_ERR_SOCKET')

  usePollLoader(1000, isBooting)

  if (isBooting) {
    return (
      <div className='bg-franka-blue-600 -mt-20 flex h-full w-full flex-col items-center justify-center gap-10'>
        <AnimatedRunningGirl inverted />
        <div className='flex h-2 w-50 items-center justify-center overflow-hidden'>
          <div className='shimmer-speed-2000 shimmer-div from-deep-sky to-deep-sky via-deep-sky-300 h-full w-full bg-linear-to-r'></div>
        </div>
      </div>
    )
  }

  let message = 'Oops!'
  let details = 'An unexpected error occurred.'
  let stack: string | undefined

  if (isRouteErrorResponse(error)) {
    message = error.status === 404 ? '404' : 'Error'
    details = error.status === 404 ? 'The requested page could not be found.' : error.statusText || details
  } else if (import.meta.env.DEV && error && error instanceof Error) {
    details = error.message
    stack = error.stack
  }

  return (
    <main className='mx-auto mt-20'>
      <Container spacing='wide'>
        <Title>{message}</Title>
        <p>{details}</p>
        {stack && (
          <pre className='w-full overflow-x-auto p-4'>
            <code>{stack}</code>
          </pre>
        )}
      </Container>
    </main>
  )
}
