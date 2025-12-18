import React from 'react'
import logo from '../assets/logo-transparent.png'
import './Header.css'

export default function Header() {
  return (
    <header className="app-header">
      <div className="header-content">
        <a 
          href="https://www.fusionaix.com/" 
          target="_blank" 
          rel="noopener noreferrer"
          className="header-logo-link"
          aria-label="Visit fusionAIx website"
        >
          <img 
            src={logo} 
            alt="fusionAIx - Unleashing Innovation" 
            className="header-logo"
          />
        </a>
      </div>
    </header>
  )
}
