import { Routes, Route } from 'react-router-dom'
import Navbar from './components/ui/Navbar'
import HomePage from './pages/HomePage'
import CalculatePage from './pages/CalculatePage'
import ReviewPage from './pages/ReviewPage'
import ResultsPage from './pages/ResultsPage'

function App(): JSX.Element {
  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />
      {/* pt-16 offsets the fixed navbar */}
      <main className="pt-16">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/calculate" element={<CalculatePage />} />
          <Route path="/review" element={<ReviewPage />} />
          <Route path="/results/:id" element={<ResultsPage />} />
          <Route path="/register" element={<div className="max-w-lg mx-auto px-4 py-16 text-center text-gray-500">Registration coming soon.</div>} />
        </Routes>
      </main>
    </div>
  )
}

export default App

