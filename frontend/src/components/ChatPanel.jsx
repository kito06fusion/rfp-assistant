import React, { useState, useEffect } from 'react'
import { usePipeline } from '../context/PipelineContext'
import ChatInterface from './ChatInterface'
import './ChatPanel.css'

export default function ChatPanel() {
  const { chatSessionId } = usePipeline()
  const [isMinimized, setIsMinimized] = useState(false)

  // Only show if there's an active session
  if (!chatSessionId) {
    return (
      <div className="chat-panel chat-panel-empty">
        <div className="chat-panel-header">
          <h3>Interactive Q&A</h3>
        </div>
        <div className="chat-panel-empty-content">
          <p>Questions will appear here after the build query is analyzed.</p>
          <p className="chat-panel-hint">The LLM will ask you for any missing information needed to generate high-quality responses.</p>
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
          />
        </div>
      )}
    </div>
  )
}

