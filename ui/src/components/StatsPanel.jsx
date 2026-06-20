import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { Database, TrendingUp, Layers, Activity } from 'lucide-react'
import axios from 'axios'
import './StatsPanel.css'

const API_BASE = 'http://localhost:8000'

function StatsPanel() {
  const [stats, setStats] = useState(null)
  const [clusters, setClusters] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [statsRes, clustersRes] = await Promise.all([
          axios.get(`${API_BASE}/api/stats`).catch(() => ({ data: null })),
          axios.get(`${API_BASE}/api/clusters`).catch(() => ({ data: [] })),
        ])
        setStats(statsRes.data)
        setClusters(clustersRes.data || [])
      } catch (e) {
        // API not available
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [])

  return (
    <motion.div
      className="stats-card"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 0.3 }}
    >
      <div className="card-header">
        <Database size={20} className="card-icon" />
        <h2>System Overview</h2>
      </div>

      {loading ? (
        <div className="stats-loading">
          <Activity size={20} className="spin" />
          <span>Connecting to backend...</span>
        </div>
      ) : !stats ? (
        <div className="stats-offline">
          <p>Backend offline — start the API server:</p>
          <code>cd api && uvicorn server:app --reload</code>
        </div>
      ) : (
        <>
          <div className="stats-grid">
            <div className="stat-item">
              <div className="stat-value">{stats.total_events?.toLocaleString() || 0}</div>
              <div className="stat-label">Total Events</div>
            </div>
            <div className="stat-item accent-cyan">
              <div className="stat-value">{stats.extracted_events?.toLocaleString() || 0}</div>
              <div className="stat-label">Extracted</div>
            </div>
            <div className="stat-item accent-purple">
              <div className="stat-value">{stats.clusters || clusters.length}</div>
              <div className="stat-label">Clusters</div>
            </div>
            <div className="stat-item accent-orange">
              <div className="stat-value">{stats.manufacturers || 0}</div>
              <div className="stat-label">Manufacturers</div>
            </div>
          </div>

          {clusters.length > 0 && (
            <div className="clusters-preview">
              <h4>
                <Layers size={14} />
                Top Clusters
              </h4>
              <div className="clusters-list">
                {clusters.slice(0, 4).map((cluster) => (
                  <div key={cluster.id} className="cluster-item">
                    <div className="cluster-item-header">
                      <span className="cluster-name">{cluster.label || `Cluster ${cluster.id}`}</span>
                      <span className="cluster-size">{cluster.size} events</span>
                    </div>
                    {cluster.trend_flag && (
                      <span className={`trend-badge trend-${cluster.trend_flag}`}>
                        <TrendingUp size={10} />
                        {cluster.trend_flag}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </motion.div>
  )
}

export default StatsPanel
