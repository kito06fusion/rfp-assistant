import React from 'react'
import './CheckboxControl.css'

export default function CheckboxControl({ id, label, checked, onChange }) {
  return (
    <div className="accept-row">
      <input
        type="checkbox"
        id={id}
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <label htmlFor={id}>{label}</label>
    </div>
  )
}

