import React from 'react'
import './StatusPill.css'

export default function StatusPill({ status, label }) {
  const getStatusClass = () => {
    switch (status) {
      case 'processing':
        return 'pill-processing'
      case 'complete':
        return 'pill-complete'
      case 'error':
        return 'pill-error'
      default:
        return ''
    }
  }

  return (
    <span className={`pill ${getStatusClass()}`}>
      {label || status}
    </span>
  )
}

