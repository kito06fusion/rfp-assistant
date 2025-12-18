import React, { useState, useEffect } from 'react'
import { usePipeline } from '../context/PipelineContext'
import AgentPanel from './AgentPanel'
import './AgentTabs.css'

const TABS = [
  { id: 'ocr', label: '1. OCR (Qwen)' },
  { id: 'preprocess', label: '2. Preprocess agent' },
  { id: 'requirements', label: '3. Requirements' },
  { id: 'build-query', label: '4. Build Query' },
  { id: 'response', label: '5. Response' },
]

export default function AgentTabs() {
  const { activeTab, setActiveTab, pipelineData } = usePipeline()

  const hasData = pipelineData.preprocess !== null

  if (!hasData) {
    return null
  }

  return (
    <section className="card" id="agents-section">
      <div className="tabs">
        {TABS.map(tab => (
          <button
            key={tab.id}
            className={`tab-button ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="columns">
        {TABS.map(tab => (
          <div
            key={tab.id}
            className={`tab-panel ${activeTab === tab.id ? 'active' : ''}`}
            id={`tab-${tab.id}`}
          >
            <AgentPanel agentId={tab.id} />
          </div>
        ))}
      </div>
    </section>
  )
}

