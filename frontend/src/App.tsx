import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import './App.css'

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/subjects" element={<div>Subjects Page (Coming Soon)</div>} />
        <Route path="/tests" element={<div>Tests Page (Coming Soon)</div>} />
        <Route path="/results" element={<div>Results Page (Coming Soon)</div>} />
        <Route path="/analysis" element={<div>Analysis Page (Coming Soon)</div>} />
      </Routes>
    </Router>
  )
}

export default App
