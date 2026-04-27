import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import TestImage from './pages/TestImage'
import TestVideo from './pages/TestVideo'
import History from './pages/History'
import Settings from './pages/Settings'

function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/test-image" element={<TestImage />} />
        <Route path="/test-video" element={<TestVideo />} />
        <Route path="/history" element={<History />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
    </Routes>
  )
}

export default App
