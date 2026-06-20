import { motion } from 'framer-motion'
import { 
  BarChart3, Tag, AlertTriangle, Layers, Users, 
  ArrowRight, Sparkles, TrendingUp 
} from 'lucide-react'
import './ResultsPanel.css'

function ExtractionResult({ data }) {
  if (!data || data.error) return null

  const fields = [
    { label: 'Modality', value: data.modality, icon: Layers },
    { label: 'Component', value: data.component, icon: Tag },
    { label: 'Failure Mode', value: data.failure_mode, icon: AlertTriangle },
    { label: 'Symptom', value: data.symptom, icon: Sparkles },
    { label: 'Severity', value: data.severity_indicator, icon: TrendingUp },
    { label: 'Patient Impact', value: data.patient_impact, icon: Users },
  ]

  return (
    <div className="result-section">
      <h3 className="section-title">
        <Sparkles size={16} />
        Extracted Fields
      </h3>
      <div className="extraction-grid">
        {fields.map((field) => {
          if (!field.value) return null
          const Icon = field.icon
          return (
            <div key={field.label} className="field-card">
              <div className="field-label">
                <Icon size={12} />
                {field.label}
              </div>
              <div className="field-value">{field.value}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function SeverityBadge({ severity }) {
  const level = severity?.replace('S', '').split('_')[0] || '?'
  const colors = { '1': 'green', '2': 'blue', '3': 'yellow', '4': 'orange', '5': 'red' }
  return (
    <span className={`severity-badge severity-${colors[level] || 'gray'}`}>
      S{level}
    </span>
  )
}

function ClusterResult({ data }) {
  if (!data || data.error) return null

  return (
    <div className="result-section">
      <h3 className="section-title">
        <Network size={16} />
        Cluster Assignment
      </h3>
      
      <div className="cluster-info">
        <div className="cluster-main">
          <span className="cluster-id">Cluster #{data.cluster_id ?? 'N/A'}</span>
          {data.cluster_label && <span className="cluster-label">{data.cluster_label}</span>}
        </div>
        {data.confidence && (
          <div className="confidence-bar">
            <div className="confidence-fill" style={{ width: `${data.confidence * 100}%` }} />
            <span>{(data.confidence * 100).toFixed(0)}%</span>
          </div>
        )}
      </div>

      {data.similar_events?.length > 0 && (
        <div className="similar-events">
          <h4>Similar Events ({data.similar_events.length})</h4>
          <div className="events-list">
            {data.similar_events.slice(0, 5).map((event, i) => (
              <div key={i} className="event-item">
                <div className="event-header">
                  <span className="event-id">{event.report_number}</span>
                  <span className="event-score">
                    {((event.similarity_score ?? event.similarity ?? 0) * 100).toFixed(0)}% match
                  </span>
                </div>
                {event.narrative_preview && (
                  <p className="event-preview">{event.narrative_preview}</p>
                )}
                <div className="event-meta">
                  {event.product_code && <span>{event.product_code}</span>}
                  {event.manufacturer && <span>{event.manufacturer}</span>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function Network({ size }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="5" r="3"/>
      <circle cx="5" cy="19" r="3"/>
      <circle cx="19" cy="19" r="3"/>
      <line x1="12" y1="8" x2="5" y2="16"/>
      <line x1="12" y1="8" x2="19" y2="16"/>
    </svg>
  )
}

function ResultsPanel({ result }) {
  if (!result) return null

  const extractionStep = result.steps?.find(s => s.step === 'extraction')
  const clusterStep = result.steps?.find(s => s.step === 'cluster_assignment')
  const embeddingStep = result.steps?.find(s => s.step === 'embedding')

  return (
    <motion.div
      className="results-card"
      initial={{ opacity: 0, y: 30 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.5 }}
    >
      <div className="card-header">
        <BarChart3 size={20} className="card-icon" />
        <h2>Analysis Results</h2>
        <span className="result-id">{result.report_id}</span>
      </div>

      {embeddingStep?.status === 'success' && (
        <div className="embedding-info">
          <div className="embedding-badge">
            <ArrowRight size={12} />
            <span>{embeddingStep.data.dimensions}D vector</span>
            <span className="separator">•</span>
            <span>norm: {embeddingStep.data.norm}</span>
          </div>
        </div>
      )}

      {extractionStep?.status === 'success' && (
        <ExtractionResult data={extractionStep.data} />
      )}

      {clusterStep?.status === 'success' && (
        <ClusterResult data={clusterStep.data} />
      )}
    </motion.div>
  )
}

export default ResultsPanel
