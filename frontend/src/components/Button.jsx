import React from 'react'
import './Button.css'

export default function Button({ children, onClick, disabled, ...props }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="action-button"
      {...props}
    >
      {children}
    </button>
  )
}

