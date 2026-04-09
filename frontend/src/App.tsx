import { BrowserRouter, Routes, Route, Navigate } from 'react-router'
import AppShell from './components/layout/AppShell'
import MediaPage from './components/media/MediaPage'
import StoryboardPage from './components/storyboard/StoryboardPage'
import EditorPage from './components/editor/EditorPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/media" element={<MediaPage />} />
          <Route path="/storyboard" element={<StoryboardPage />} />
          <Route path="/editor" element={<EditorPage />} />
          <Route path="*" element={<Navigate to="/media" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
