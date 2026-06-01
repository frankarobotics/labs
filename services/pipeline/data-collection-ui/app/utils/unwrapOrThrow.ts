import type { FetchResponse } from 'openapi-fetch'
import { data } from 'react-router'

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null

const hasString = <K extends string>(o: Record<string, unknown>, k: K): o is Record<K, string> =>
  typeof o[k] === 'string'

const hasNumber = <K extends string>(o: Record<string, unknown>, k: K): o is Record<K, number> =>
  typeof o[k] === 'number'

const hasCause = (o: Record<string, unknown>): o is Record<'cause', unknown> => 'cause' in o

function extractSystemError(err: unknown): {
  code?: string
  errno?: number
  syscall?: string
  address?: string
  port?: number
} {
  const out: { code?: string; errno?: number; syscall?: string; address?: string; port?: number } = {}
  const seen = new Set<unknown>()
  let cur: unknown = err

  while (isObj(cur) && !seen.has(cur)) {
    seen.add(cur)
    if ('code' in cur && hasString(cur, 'code')) out.code = cur.code
    if ('errno' in cur && hasNumber(cur, 'errno')) out.errno = cur.errno
    if ('syscall' in cur && hasString(cur, 'syscall')) out.syscall = cur.syscall
    if ('address' in cur && hasString(cur, 'address')) out.address = cur.address
    if ('port' in cur && hasNumber(cur, 'port')) out.port = cur.port
    cur = hasCause(cur) ? cur.cause : undefined
  }
  return out
}

function isAbortError(err: unknown): boolean {
  // In web/Node fetch, aborts reject with (a) DOMException named "AbortError"
  // or a Node AbortError that at least has name === "AbortError".
  return (
    (err instanceof DOMException && err.name === 'AbortError') ||
    (isObj(err) && 'name' in err && hasString(err, 'name') && err.name === 'AbortError')
  )
}

type DataFrom<R> = Extract<Awaited<R>, { data: unknown }>['data']

export default async function unwrapOrThrow<
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  R extends Promise<FetchResponse<any, any, any>>,
>(
  promise: R,
  opts?: { onHttpError?: (res: Awaited<R>) => void | never },
  label: string = 'Upstream',
): Promise<DataFrom<R>> {
  try {
    const res = await promise
    if (res.error) {
      opts?.onHttpError?.(res)
      throw data(
        { message: `${label} returned ${res.response?.status ?? 'error'}`, upstream: res.error },
        { status: res.response?.status ?? 502 },
      )
    }
    return res.data
  } catch (e: unknown) {
    if (isAbortError(e)) {
      throw data({ message: `${label} request aborted` }, { status: 499 })
    }

    const sys = extractSystemError(e)

    if (typeof e === 'object' && e instanceof DOMException && e.name === 'TimeoutError') throw e

    const message =
      sys.code === 'ECONNREFUSED' ? `${label} unreachable (connection refused)` : `${label} network failure`
    const status = sys.code === 'ECONNREFUSED' ? 503 : 502

    console.error(`${label} failed`, e)

    throw data({ message, ...sys }, { status })
  }
}
