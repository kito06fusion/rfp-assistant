import React from 'react'
import './Button.css'

export default function Button({ children, onClick, disabled, className = '', ...props }) {
  const combinedClassName = `action-button ${className}`.trim()
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={combinedClassName}
      {...props}
    >
      {children}
    </button>
  )
}

