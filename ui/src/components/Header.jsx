import { motion } from 'framer-motion'
import { Activity, Shield, Zap } from 'lucide-react'
import './Header.css'

function Header() {
  return (
    <motion.header
      className="header"
      initial={{ y: -20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.5 }}
    >
      <div className="header-content">
        <div className="logo-section">
          <div className="logo-icon">
            <Shield size={24} />
          </div>
          <div className="logo-text">
            <h1>Signal Intelligence</h1>
            <span className="subtitle">Medical Device Complaint Analysis Pipeline</span>
          </div>
        </div>
        <div className="header-badges">
          <div className="badge">
            <Activity size={14} />
            <span>Real-time Processing</span>
          </div>
          <div className="badge accent">
            <Zap size={14} />
            <span>AI-Powered Extraction</span>
          </div>
        </div>
      </div>
    </motion.header>
  )
}

export default Header
