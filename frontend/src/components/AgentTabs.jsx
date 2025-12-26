import React from 'react'
import { usePipeline } from '../context/PipelineContext'
import AgentPanel from './AgentPanel'
import './AgentTabs.css'

// Icon components
const OcrIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
    <line x1="9" y1="3" x2="9" y2="21"/>
    <line x1="15" y1="3" x2="15" y2="21"/>
    <line x1="3" y1="9" x2="21" y2="9"/>
    <line x1="3" y1="15" x2="21" y2="15"/>
  </svg>
)

const FilterIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>
  </svg>
)

const ListIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="8" y1="6" x2="21" y2="6"/>
    <line x1="8" y1="12" x2="21" y2="12"/>
    <line x1="8" y1="18" x2="21" y2="18"/>
    <line x1="3" y1="6" x2="3.01" y2="6"/>
    <line x1="3" y1="12" x2="3.01" y2="12"/>
    <line x1="3" y1="18" x2="3.01" y2="18"/>
  </svg>
)

const WandIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M15 4V2m0 2v2m0-2h-2m2 0h2M7 20v2m0-2v-2m0 2H5m2 0h2M5 4h2m-2 0v2m0-2V2m14 14h2m-2 0h-2m2 0v2m0-2v-2M9 9l5 5m0-5l-5 5"/>
  </svg>
)

const DocumentIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
    <polyline points="14 2 14 8 20 8"/>
    <line x1="16" y1="13" x2="8" y2="13"/>
    <line x1="16" y1="17" x2="8" y2="17"/>
    <polyline points="10 9 9 9 8 9"/>
  </svg>
)

const TABS = [
  { id: 'ocr', label: 'OCR', icon: OcrIcon },
  { id: 'preprocess', label: 'Preprocess', icon: FilterIcon },
  { id: 'requirements', label: 'Requirements', icon: ListIcon },
  { id: 'build-query', label: 'Build Query', icon: WandIcon },
  { id: 'response', label: 'Response', icon: DocumentIcon },
]

export default function AgentTabs() {
  const { activeTab, setActiveTab, pipelineData } = usePipeline()

  const hasData = pipelineData.ocr !== null || pipelineData.preprocess !== null

  if (!hasData) {
    return null
  }

  return (
    <section id="agents-section" className="agents-section">
      <div className="tabs-container">
        <div className="tabs">
          {TABS.map(tab => {
            const Icon = tab.icon
            return (
              <button
                key={tab.id}
                className={`tab-button ${activeTab === tab.id ? 'active' : ''}`}
                onClick={() => setActiveTab(tab.id)}
              >
                <span className="tab-icon">
                  <Icon />
                </span>
                <span className="tab-label">{tab.label}</span>
              </button>
            )
          })}
        </div>
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

