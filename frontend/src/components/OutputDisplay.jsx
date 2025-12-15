import React from 'react'
import './OutputDisplay.css'

export default function OutputDisplay({ content, placeholder = 'Waiting...' }) {
  return (
    <pre className="output-display">
      {content || placeholder}
    </pre>
  )
}

