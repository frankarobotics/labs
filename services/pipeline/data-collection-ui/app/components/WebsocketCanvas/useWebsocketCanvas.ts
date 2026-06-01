import { useEffect, useReducer, useRef } from 'react'

/* ────────────────────────────────────────────────────────────────────────── *
 * Types & reducer
 * ────────────────────────────────────────────────────────────────────────── */

export type WsCanvasStatus =
  | { kind: 'idle' }
  | { kind: 'connecting' }
  | { kind: 'open' }
  | { kind: 'closed'; code?: number; reason?: string; wasClean?: boolean }
  | { kind: 'error'; message: string }

export type UseWebSocketCanvasOptions = {
  url?: string
  canvasRef: React.RefObject<HTMLCanvasElement | null>
  aspectRatio?: number
  background?: string
  disabled?: boolean
}

type Action =
  | { type: 'IDLE' }
  | { type: 'CONNECTING' }
  | { type: 'OPEN' }
  | { type: 'CLOSED'; code?: number; reason?: string; wasClean?: boolean }
  | { type: 'ERROR'; message: string }

function statusReducer(_: WsCanvasStatus, a: Action): WsCanvasStatus {
  switch (a.type) {
    case 'IDLE':
      return { kind: 'idle' }
    case 'CONNECTING':
      return { kind: 'connecting' }
    case 'OPEN':
      return { kind: 'open' }
    case 'CLOSED':
      return { kind: 'closed', code: a.code, reason: a.reason, wasClean: a.wasClean }
    case 'ERROR':
      return { kind: 'error', message: a.message }
  }
}

/* ────────────────────────────────────────────────────────────────────────── *
 * Ref bundle used by external helpers
 * ────────────────────────────────────────────────────────────────────────── */

type RefBundle = {
  canvasRef: React.RefObject<HTMLCanvasElement | null>
  ctxRef: React.RefObject<CanvasRenderingContext2D | null>
  wsRef: React.RefObject<WebSocket | null>
  decodingRef: React.RefObject<boolean>
  latestBlobRef: React.RefObject<Blob | null>
  disposedRef: React.RefObject<boolean>
  options: {
    aspectRatio?: number
    background: string
  }
}

/* ────────────────────────────────────────────────────────────────────────── *
 * Module-scope feature detection
 * ────────────────────────────────────────────────────────────────────────── */

const HAS_CREATE_IMAGE_BITMAP: boolean = typeof window !== 'undefined' && 'createImageBitmap' in window

function ensure2DContext({ canvasRef, ctxRef }: RefBundle): CanvasRenderingContext2D | null {
  const canvas = canvasRef.current
  if (!canvas) return null
  if (!ctxRef.current) {
    const ctx = canvas.getContext('2d', { alpha: false })
    if (!ctx) return null
    ctx.imageSmoothingEnabled = true
    ctx.imageSmoothingQuality = 'low'
    ctxRef.current = ctx
  }
  return ctxRef.current
}

/* ────────────────────────────────────────────────────────────────────────── *
 * Helpers
 * ────────────────────────────────────────────────────────────────────────── */

async function decodeBlobToSource(blob: Blob): Promise<ImageBitmap | HTMLImageElement> {
  if (HAS_CREATE_IMAGE_BITMAP) {
    const bmp = await createImageBitmap(blob)
    return bmp // caller closes if applicable
  }
  // Fallback: <img> + object URL
  return await new Promise<HTMLImageElement>((resolve, reject) => {
    const url = URL.createObjectURL(blob)
    const img = new Image()
    const revokeTimer = setTimeout(() => URL.revokeObjectURL(url), 5000)
    img.onload = () => {
      clearTimeout(revokeTimer)
      URL.revokeObjectURL(url)
      resolve(img)
    }
    img.onerror = () => {
      clearTimeout(revokeTimer)
      URL.revokeObjectURL(url)
      reject(new Error('Image decode failed'))
    }
    img.src = url
  })
}

function paintToCanvas(bundle: RefBundle, source: ImageBitmap | HTMLImageElement): void {
  const canvas = bundle.canvasRef.current
  const ctx = ensure2DContext(bundle)
  if (!canvas || !ctx) return

  const dpr = typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1
  const displayW = Math.max(1, Math.floor(canvas.clientWidth))
  const displayH = Math.max(1, Math.floor(canvas.clientHeight))
  const targetW = displayW * dpr
  const targetH = displayH * dpr

  if (canvas.width !== targetW || canvas.height !== targetH) {
    canvas.width = targetW
    canvas.height = targetH
  }

  ctx.save()
  ctx.fillStyle = bundle.options.background
  ctx.fillRect(0, 0, canvas.width, canvas.height)

  const srcW = source.width
  const srcH = source.height

  // Optional letterboxed inner box respecting aspectRatio
  let boxW = canvas.width
  let boxH = canvas.height
  const { aspectRatio } = bundle.options
  if (aspectRatio && aspectRatio > 0) {
    const boxRatio = canvas.width / canvas.height
    if (boxRatio > aspectRatio) {
      boxH = canvas.height
      boxW = Math.round(boxH * aspectRatio)
    } else {
      boxW = canvas.width
      boxH = Math.round(boxW / aspectRatio)
    }
  }

  const scale = Math.min(boxW / srcW, boxH / srcH)
  const drawW = Math.round(srcW * scale)
  const drawH = Math.round(srcH * scale)

  const boxX = Math.floor((canvas.width - boxW) / 2)
  const boxY = Math.floor((canvas.height - boxH) / 2)
  const dx = boxX + Math.floor((boxW - drawW) / 2)
  const dy = boxY + Math.floor((boxH - drawH) / 2)

  ctx.drawImage(source, dx, dy, drawW, drawH)
  ctx.restore()
}

function maybeProcessFrame(bundle: RefBundle): void {
  if (bundle.decodingRef.current || bundle.disposedRef.current) return
  const blob = bundle.latestBlobRef.current
  if (!blob) return

  // Consume slot
  bundle.latestBlobRef.current = null
  bundle.decodingRef.current = true

  decodeBlobToSource(blob)
    .then((source) => {
      if (bundle.disposedRef.current) {
        // Clean up decoded resource even if we won't paint
        if ('close' in source && typeof source.close === 'function') {
          try {
            ;(source as ImageBitmap).close()
          } catch {
            // do nothing
          }
        }
        return
      }
      // Paint synchronized with rendering
      requestAnimationFrame(() => {
        try {
          paintToCanvas(bundle, source)
        } finally {
          if ('close' in source && typeof source.close === 'function') {
            try {
              ;(source as ImageBitmap).close()
            } catch {
              // do nothing
            }
          }
        }
      })
    })
    .catch((err) => {
      // Drop only the bad frame; keep stream alive

      console.warn('[useWebSocketCanvas] Decode error:', err)
    })
    .finally(() => {
      bundle.decodingRef.current = false
      if (!bundle.disposedRef.current && bundle.latestBlobRef.current) {
        // Rather than recursively calling maybeProcessFrame
        // run maybeProcessFrame in the next microtask queue
        // Microtask hop prevents recursive growth under floods
        Promise.resolve().then(() => maybeProcessFrame(bundle))
      }
    })
}

export function useWebSocketCanvas(opts: UseWebSocketCanvasOptions): WsCanvasStatus {
  const { url, canvasRef, aspectRatio, background = '#F6F8F8', disabled } = opts

  const [status, dispatch] = useReducer(statusReducer, { kind: 'idle' })

  const wsRef = useRef<WebSocket | null>(null)
  const disposedRef = useRef<boolean>(false)
  const decodingRef = useRef<boolean>(false)
  const latestBlobRef = useRef<Blob | null>(null)
  const ctxRef = useRef<CanvasRenderingContext2D | null>(null)
  const hiddenRef = useRef<boolean>(false)

  useEffect(() => {
    disposedRef.current = false

    if (disabled || !url || !canvasRef.current) {
      dispatch({ type: 'IDLE' })
      return
    }

    // bundle refs to pass to external helper functions
    const bundle: RefBundle = {
      canvasRef,
      ctxRef,
      wsRef,
      decodingRef,
      latestBlobRef,
      disposedRef,
      options: { aspectRatio, background },
    }

    // Prepare context early to avoid races with first frame
    ensure2DContext(bundle)

    function handleVisibility() {
      hiddenRef.current = document.hidden
      if (hiddenRef.current) {
        // Stop any in-flight decode, drop queued frame
        latestBlobRef.current = null
      } else {
        ensure2DContext(bundle)
        Promise.resolve().then(() => maybeProcessFrame(bundle))
      }
    }

    document.addEventListener('visibilitychange', handleVisibility)

    hiddenRef.current = typeof document !== 'undefined' ? document.hidden : false

    // Open WebSocket
    let ws: WebSocket | null = null
    try {
      ws = new WebSocket(url)
    } catch (e: unknown) {
      if (e instanceof Error) dispatch({ type: 'ERROR', message: e?.message })
      else dispatch({ type: 'ERROR', message: 'Invalid WebSocket URL' })
      return
    }
    wsRef.current = ws
    ws.binaryType = 'blob'
    dispatch({ type: 'CONNECTING' })

    ws.onopen = () => dispatch({ type: 'OPEN' })

    ws.onerror = () => {
      // onerror has no detail; onclose typically follows with details
      dispatch({ type: 'ERROR', message: 'WebSocket error' })
    }

    ws.onclose = (ev) => {
      dispatch({ type: 'CLOSED', code: ev.code, reason: ev.reason, wasClean: ev.wasClean })
    }

    ws.onmessage = (ev: MessageEvent) => {
      // do not render anything if the page is not visible or being torn down
      if (disposedRef.current || hiddenRef.current) return

      let blob: Blob | null = null
      if (ev.data instanceof Blob) {
        blob = ev.data
      } else if (ev.data instanceof ArrayBuffer) {
        blob = new Blob([ev.data], { type: 'image/jpeg' })
      } else {
        // Ignore text/control messages
        return
      }

      // Latest-frame-wins single-slot buffer
      latestBlobRef.current = blob
      maybeProcessFrame(bundle)
    }

    // Cleanup
    return () => {
      disposedRef.current = true
      if (wsRef.current) {
        try {
          wsRef.current.close()
        } catch {
          // do nothing
        }
      }
      wsRef.current = null
      latestBlobRef.current = null
      ctxRef.current = null
    }
  }, [url, canvasRef, disabled, background, aspectRatio])

  return status
}
