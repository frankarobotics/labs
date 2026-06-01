import { type Cookie, type CookieSerializeOptions } from 'react-router'

/**
 * A helper to keep track of cookie state in the
 * scope of a loader / action. Stores all mutations
 * to a cookie in a map and holds a public headers
 * object that can be passed to any response.
 * When getting a value, will return the stored
 * map value, or fall back to cookie value in initial
 * Request, if it exists.
 */
export class CookieScope {
  private staged = new Map<string, unknown>()
  private request: Request
  headers: Headers

  constructor(request: Request, headers?: Headers) {
    this.request = request
    this.headers = headers ?? new Headers()
  }

  async get(cookie: Cookie): Promise<unknown> {
    if (this.staged.has(cookie.name)) {
      return this.staged.get(cookie.name) as string | null
    }
    const incoming = await cookie.parse(this.request.headers.get('Cookie'))
    return incoming
  }

  async set(cookie: Cookie, value: unknown, opts?: CookieSerializeOptions) {
    this.staged.set(cookie.name, value)
    const setCookie = await cookie.serialize(value, opts)
    this.headers.append('Set-Cookie', setCookie)
  }

  async clear(cookie: Cookie, opts?: CookieSerializeOptions) {
    this.staged.delete(cookie.name)
    const setCookie = await cookie.serialize('', { ...opts, maxAge: 0 })
    this.headers.append('Set-Cookie', setCookie)
  }
}
