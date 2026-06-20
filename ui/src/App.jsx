import { useState } from 'react'
import { AnimatePresence } from 'framer-motion'
import Header from './components/Header'
import ComplaintForm from './components/ComplaintForm'
import PipelineVisualizer from './components/PipelineVisualizer'
import ResultsPanel from './components/ResultsPanel'
import './App.css'

function App() {
  const [pipelineResult, setPipelineResult] = useState(null)
  const [isProcessing, setIsProcessing] = useState(false)
  const [currentStep, setCurrentStep] = useState(null)

  return (
    <div className="app">
      <Header />
      <main className="main-content">
        <div className="left-panel">
          <ComplaintForm
            onResult={setPipelineResult}
            onProcessing={setIsProcessing}
            onStepChange={setCurrentStep}
          />
        </div>
        <div className="right-panel">
          <PipelineVisualizer
            isProcessing={isProcessing}
            currentStep={currentStep}
            result={pipelineResult}
          />
          <AnimatePresence>
            {pipelineResult && (
              <ResultsPanel result={pipelineResult} />
            )}
          </AnimatePresence>
        </div>
      </main>
    </div>
  )
}

export default App
