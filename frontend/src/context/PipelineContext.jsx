import React, { createContext, useContext, useState, useCallback } from 'react'

const PipelineContext = createContext()

export function usePipeline() {
  const context = useContext(PipelineContext)
  if (!context) {
    throw new Error('usePipeline must be used within a PipelineProvider')
  }
  return context
}

export function PipelineProvider({ children }) {
  const [pipelineData, setPipelineData] = useState({
    ocr: null,
    preprocess: null,
    requirements: null,
    buildQuery: null,
    response: null,
  })

  const [activeTab, setActiveTab] = useState('ocr')
  const [statuses, setStatuses] = useState({
    preprocess: 'waiting',
    requirements: 'waiting',
    buildQuery: 'waiting',
    response: 'waiting',
  })

  const [confirmations, setConfirmations] = useState({
    preprocessConfirmed: false,
    buildQueryConfirmed: false,
  })
  const [editable, setEditable] = useState({
    preprocess: false,
    requirements: false,
    buildQuery: false,
  })
  
  const [chatSessionId, setChatSessionId] = useState(null)
  const [allQuestionsAnswered, setAllQuestionsAnswered] = useState(false)

  const updatePipelineData = useCallback((key, value) => {
    setPipelineData(prev => ({ ...prev, [key]: value }))
  }, [])

  const updateStatus = useCallback((agent, status) => {
    setStatuses(prev => ({ ...prev, [agent]: status }))
  }, [])

  const updateConfirmation = useCallback((key, value) => {
    setConfirmations(prev => ({ ...prev, [key]: value }))
  }, [])

  const updateEditable = useCallback((key, value) => {
    setEditable(prev => ({ ...prev, [key]: value }))
  }, [])

  const resetPipeline = useCallback(() => {
    setPipelineData({
      ocr: null,
      preprocess: null,
      requirements: null,
      buildQuery: null,
      response: null,
    })
    setStatuses({
      preprocess: 'waiting',
      requirements: 'waiting',
      buildQuery: 'waiting',
      response: 'waiting',
    })
    setConfirmations({
      preprocessConfirmed: false,
      buildQueryConfirmed: false,
    })
    setEditable({
      preprocess: false,
      requirements: false,
      buildQuery: false,
    })
    setChatSessionId(null)
    setAllQuestionsAnswered(false)
    setActiveTab('ocr')
  }, [])

  return (
    <PipelineContext.Provider
      value={{
        pipelineData,
        updatePipelineData,
        activeTab,
        setActiveTab,
        statuses,
        updateStatus,
        confirmations,
        updateConfirmation,
        editable,
        updateEditable,
        resetPipeline,
        chatSessionId,
        setChatSessionId,
        allQuestionsAnswered,
        setAllQuestionsAnswered,
      }}
    >
      {children}
    </PipelineContext.Provider>
  )
}

