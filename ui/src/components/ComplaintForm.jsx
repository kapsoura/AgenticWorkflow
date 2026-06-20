import { useState } from 'react'
import { motion } from 'framer-motion'
import { Send, FileText, AlertTriangle, Loader2 } from 'lucide-react'
import axios from 'axios'
import './ComplaintForm.css'

const API_BASE = 'http://localhost:8000'

const SAMPLE_COMPLAINTS = [
  {
    label: 'MRI Image Artifact',
    text: 'During routine brain scan, the MRI system displayed significant ghosting artifacts on T2-weighted sequences. The images were non-diagnostic and the patient had to be rescanned. The artifact appeared after a recent software update to version 4.2.1. Similar issues reported on two other scanners at our facility.',
  },
  {
    label: 'CT Scanner Shutdown',
    text: 'The CT scanner unexpectedly shut down mid-scan while performing a cardiac CT angiography. The patient was on the table and the contrast agent had already been injected. The system displayed error code E-4401 before powering off. Required manual restart and patient had to be rescheduled.',
  },
  {
    label: 'Ultrasound Probe Failure',
    text: 'Linear ultrasound probe L12-3 intermittently loses signal during abdominal examinations. The display goes black for 2-3 seconds before recovering. This has occurred 5 times in the past week across different patients. No error messages are displayed. Probe connector appears intact.',
  },
]

function ComplaintForm({ onResult, onProcessing, onStepChange }) {
  const [narrative, setNarrative] = useState('')
  const [reportId, setReportId] = useState('')
  const [runExtraction, setRunExtraction] = useState(true)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!narrative.trim()) return

    setIsLoading(true)
    setError(null)
    onProcessing(true)
    onResult(null)
    onStepChange('extraction')

    try {
      const response = await axios.post(`${API_BASE}/api/process`, {
        narrative: narrative.trim(),
        report_id: reportId || `UI-${Date.now()}`,
        skip_extraction: !runExtraction,
      })

      // Simulate step progression for visualization
      const steps = response.data.steps
      for (let i = 0; i < steps.length; i++) {
        onStepChange(steps[i].step)
        await new Promise(resolve => setTimeout(resolve, 300))
      }

      onResult(response.data)
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to process complaint')
    } finally {
      setIsLoading(false)
      onProcessing(false)
      onStepChange(null)
    }
  }

  const loadSample = (sample) => {
    setNarrative(sample.text)
    setReportId('')
  }

  return (
    <motion.div
      className="complaint-form-card"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 0.1 }}
    >
      <div className="card-header">
        <FileText size={20} className="card-icon" />
        <h2>Submit Complaint</h2>
      </div>

      <div className="sample-buttons">
        <span className="sample-label">Quick samples:</span>
        {SAMPLE_COMPLAINTS.map((sample, i) => (
          <button
            key={i}
            className="sample-btn"
            onClick={() => loadSample(sample)}
            type="button"
          >
            {sample.label}
          </button>
        ))}
      </div>

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="narrative">Complaint Narrative</label>
          <textarea
            id="narrative"
            value={narrative}
            onChange={(e) => setNarrative(e.target.value)}
            placeholder="Enter the medical device complaint narrative here..."
            rows={6}
            required
          />
          <span className="char-count">{narrative.length} characters</span>
        </div>

        <div className="form-row">
          <div className="form-group">
            <label htmlFor="reportId">Report ID (optional)</label>
            <input
              id="reportId"
              type="text"
              value={reportId}
              onChange={(e) => setReportId(e.target.value)}
              placeholder="e.g., MDR-2024-001"
            />
          </div>

          <div className="form-group toggle-group">
            <label>
              <input
                type="checkbox"
                checked={runExtraction}
                onChange={(e) => setRunExtraction(e.target.checked)}
              />
              <span className="toggle-switch"></span>
              Run LLM Extraction
            </label>
          </div>
        </div>

        {error && (
          <motion.div
            className="error-message"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
          >
            <AlertTriangle size={16} />
            <span>{error}</span>
          </motion.div>
        )}

        <button
          type="submit"
          className="submit-btn"
          disabled={isLoading || !narrative.trim()}
        >
          {isLoading ? (
            <>
              <Loader2 size={18} className="spin" />
              Processing...
            </>
          ) : (
            <>
              <Send size={18} />
              Process Complaint
            </>
          )}
        </button>
      </form>
    </motion.div>
  )
}

export default ComplaintForm
