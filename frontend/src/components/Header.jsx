import React from 'react'
import { usePipeline } from '../context/PipelineContext'
import logo from '../assets/logo-transparent.png'
import './Header.css'

export default function Header() {
  const { pipelineData } = usePipeline()
  
  const getFileNameWithoutExtension = (fileName) => {
    if (!fileName) return ''
    const lastDotIndex = fileName.lastIndexOf('.')
    if (lastDotIndex === -1) return fileName
    return fileName.substring(0, lastDotIndex)
  }
  
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
        {pipelineData.ocr && pipelineData.uploadedFileName && (
          <div className="header-filename" title={pipelineData.uploadedFileName}>
            {getFileNameWithoutExtension(pipelineData.uploadedFileName)}
          </div>
        )}
      </div>
    </header>
  )
}
