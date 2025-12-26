import React from 'react'
import { PipelineProvider, usePipeline } from './context/PipelineContext'
import ErrorBoundary from './components/ErrorBoundary'
import Header from './components/Header'
import UploadSection from './components/UploadSection'
import ProgressTracker from './components/ProgressTracker'
import AgentTabs from './components/AgentTabs'
import ChatPanel from './components/ChatPanel'
import './App.css'

function AppContent() {
  const { pipelineData } = usePipeline()
  const showUpload = !pipelineData.ocr

  return (
    <main className="app-main">
      <div className="unified-container">
        <Header />
        <div className="layout">
          <div className="main-content">
            <ProgressTracker />
            {showUpload && (
              <>
                <hr className="section-divider" />
                <UploadSection />
              </>
            )}
            <hr className="section-divider" />
            <AgentTabs />
          </div>
          <div className="chat-sidebar">
            <ChatPanel />
          </div>
        </div>
      </div>
    </main>
  )
}

function App() {
  return (
    <ErrorBoundary>
      <PipelineProvider>
        <AppContent />
      </PipelineProvider>
    </ErrorBoundary>
  )
}

export default App

