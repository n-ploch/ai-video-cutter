import { useEffect, useRef } from 'react'

/**
 * Generic polling hook. Calls `fn` every `intervalMs` milliseconds.
 * Stops when `shouldStop` returns true or component unmounts.
 */
export function usePolling(
  fn: () => Promise<void> | void,
  intervalMs: number,
  shouldStop: boolean,
) {
  const fnRef = useRef(fn)
  fnRef.current = fn

  useEffect(() => {
    if (shouldStop) return

    // Call immediately on mount
    fnRef.current()

    const id = setInterval(() => {
      fnRef.current()
    }, intervalMs)

    return () => clearInterval(id)
  }, [intervalMs, shouldStop])
}
