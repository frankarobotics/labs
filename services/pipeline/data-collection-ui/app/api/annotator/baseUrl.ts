// Only this server calls the annotator, so the target never follows a request's Host (the UI runs on host network)
export function annotatorBaseUrl(port: string | undefined): URL | null {
  if (!port) return null
  if (!/^\d+$/.test(port) || Number(port) < 1 || Number(port) > 65535) {
    throw new Error(`NOMADIC_EPISODE_ANNOTATOR_PORT must be a TCP port, got ${JSON.stringify(port)}`)
  }
  return new URL(`http://127.0.0.1:${port}`)
}
