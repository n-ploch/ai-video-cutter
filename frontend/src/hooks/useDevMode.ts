export function useDevMode(): boolean {
  return import.meta.env.VITE_DEV_MODE === 'true'
}
