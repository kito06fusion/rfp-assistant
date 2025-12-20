import React, { useState, useEffect } from 'react'
import { usePipeline } from '../context/PipelineContext'
import ChatInterface from './ChatInterface'
import './ChatPanel.css'

export default function ChatPanel() {
  const { chatSessionId, pipelineData, updatePipelineData, setAllQuestionsAnswered } = usePipeline()
  const [isMinimized, setIsMinimized] = useState(false)

  const handleBuildQueryUpdated = (updatedBuildQuery) => {
    if (!updatedBuildQuery) return
    updatePipelineData('buildQuery', updatedBuildQuery)
  }
  
  const handleAllAnswered = () => {
    console.log('All critical questions answered!')
    setAllQuestionsAnswered(true)
  }

  // Only show if there's an active session
  if (!chatSessionId) {
    return (
      <div className="chat-panel chat-panel-empty">
        <div className="chat-panel-header">
          <h3>Interactive Q&A</h3>
        </div>
        <div className="chat-panel-empty-content">
          <p>Questions will appear here after confirming the build query.</p>
          <p className="chat-panel-hint">The system searches RAG first, then asks only critical questions one at a time.</p>
        </div>
      </div>
    )
  }

  return (
    <div className={`chat-panel ${isMinimized ? 'chat-panel-minimized' : ''}`}>
      <div className="chat-panel-header">
        <h3>Interactive Q&A</h3>
        <button 
          className="chat-panel-toggle"
          onClick={() => setIsMinimized(!isMinimized)}
          aria-label={isMinimized ? 'Expand chat' : 'Minimize chat'}
        >
          {isMinimized ? '↑' : '↓'}
        </button>
      </div>
      {!isMinimized && (
        <div className="chat-panel-content">
          <ChatInterface 
            sessionId={chatSessionId} 
            onClose={null}
            buildQuery={pipelineData.buildQuery}
            onBuildQueryUpdated={handleBuildQueryUpdated}
            requirements={pipelineData.requirements}
            iterativeMode={true}
            onAllAnswered={handleAllAnswered}
          />
        </div>
      )}
    </div>
  )
}

