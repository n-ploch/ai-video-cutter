import { create } from 'zustand'

interface UiStore {
  sidebarCollapsed: boolean
  toggleSidebar: () => void
}

export const useUiStore = create<UiStore>((set) => ({
  sidebarCollapsed: false,
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
}))
