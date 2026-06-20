import { motion } from 'framer-motion'
import { Brain, Cpu, Network, CheckCircle2, XCircle, Loader2, SkipForward } from 'lucide-react'
import './PipelineVisualizer.css'

const PIPELINE_STEPS = [
  { id: 'extraction', label: 'LLM Extraction', icon: Brain, description: 'AI extracts structured fields from narrative' },
  { id: 'embedding', label: 'BGE Embedding', icon: Cpu, description: 'Generate 1024-dim semantic vector' },
  { id: 'cluster_assignment', label: 'Cluster Analysis', icon: Network, description: 'Find similar events & assign cluster' },
]

function getStepStatus(step, result, currentStep, isProcessing) {
  if (!result && !isProcessing) return 'idle'
  if (result) {
    const stepResult = result.steps?.find(s => s.step === step.id)
    if (stepResult) return stepResult.status
    return 'idle'
  }
  if (currentStep === step.id) return 'processing'
  const currentIdx = PIPELINE_STEPS.findIndex(s => s.id === currentStep)
  const stepIdx = PIPELINE_STEPS.findIndex(s => s.id === step.id)
  if (stepIdx < currentIdx) return 'success'
  return 'waiting'
}

function StatusIcon({ status }) {
  switch (status) {
    case 'success': return <CheckCircle2 size={16} className="status-icon success" />
    case 'error': return <XCircle size={16} className="status-icon error" />
    case 'processing': return <Loader2 size={16} className="status-icon processing spin" />
    case 'skipped': return <SkipForward size={16} className="status-icon skipped" />
    default: return <div className="status-dot" />
  }
}

function PipelineVisualizer({ isProcessing, currentStep, result }) {
  return (
    <motion.div
      className="pipeline-card"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 0.2 }}
    >
      <div className="card-header">
        <Network size={20} className="card-icon" />
        <h2>Processing Pipeline</h2>
        {result && (
          <span className="total-time">{result.total_duration_ms}ms total</span>
        )}
      </div>

      <div className="pipeline-steps">
        {PIPELINE_STEPS.map((step, index) => {
          const status = getStepStatus(step, result, currentStep, isProcessing)
          const StepIcon = step.icon
          const stepResult = result?.steps?.find(s => s.step === step.id)

          return (
            <div key={step.id}>
              <motion.div
                className={`pipeline-step ${status}`}
                animate={status === 'processing' ? { scale: [1, 1.02, 1] } : {}}
                transition={{ repeat: Infinity, duration: 1.5 }}
              >
                <div className="step-icon-wrapper">
                  <StepIcon size={20} />
                </div>
                <div className="step-info">
                  <div className="step-header">
                    <span className="step-label">{step.label}</span>
                    <StatusIcon status={status} />
                  </div>
                  <span className="step-description">{step.description}</span>
                  {stepResult && stepResult.status !== 'skipped' && (
                    <span className="step-duration">{stepResult.duration_ms}ms</span>
                  )}
                </div>
              </motion.div>
              {index < PIPELINE_STEPS.length - 1 && (
                <div className={`pipeline-connector ${status === 'success' ? 'active' : ''}`}>
                  <div className="connector-line" />
                </div>
              )}
            </div>
          )
        })}
      </div>
    </motion.div>
  )
}

export default PipelineVisualizer
