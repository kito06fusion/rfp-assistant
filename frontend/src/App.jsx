import React from 'react'
import { PipelineProvider } from './context/PipelineContext'
import ErrorBoundary from './components/ErrorBoundary'
import Header from './components/Header'
import UploadSection from './components/UploadSection'
import ProgressTracker from './components/ProgressTracker'
import AgentTabs from './components/AgentTabs'
import ChatPanel from './components/ChatPanel'
import './App.css'

function App() {
  return (
    <ErrorBoundary>
      <PipelineProvider>
        <Header />
        <main className="app-main">
          <div className="layout">
            <div className="main-content">
              <UploadSection />
              <ProgressTracker />
              <AgentTabs />
            </div>
            <div className="chat-sidebar">
              <ChatPanel />
            </div>
          </div>
        </main>
      </PipelineProvider>
    </ErrorBoundary>
  )
}

export default App

