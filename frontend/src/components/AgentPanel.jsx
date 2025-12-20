import React, { useEffect, useState } from 'react'
import { usePipeline } from '../context/PipelineContext'
import { runRequirements, buildQuery, generateResponse, generateQuestions, createChatSession, addQuestionsToSession, previewResponses, updateResponse, generatePDFFromPreview, updateRequirements, getSession } from '../services/api'
import StatusPill from './StatusPill'
import OutputDisplay from './OutputDisplay'
import Button from './Button'
import ChatInterface from './ChatInterface'
import ResponsePreview from './ResponsePreview'
import { formatPreprocessOutput, formatRequirementsOutput } from '../utils/formatters'
import './AgentPanel.css'

const AGENT_CONFIGS = {
  ocr: {
    title: '1. Raw OCR Text',
    description: 'Full text extracted from the original PDF/DOCX. Uses direct text readers when possible, falls back to Qwen vision model for scanned/image-based documents.',
    badge: null,
    showStatus: false,
  },
  preprocess: {
    title: '2. Preprocess Agent',
    pillLabel: 'gpt-5-chat',
    badge: 'Cleaned text + removed content + CPV / summary',
    showStatus: true,
  },
  requirements: {
    title: '3. Requirements Agent',
    pillLabel: 'gpt-5-chat',
    badge: 'Solution vs response-structure requirements',
    showStatus: true,
    showBuildQuery: true,
  },
  'build-query': {
    title: '4. Build Query',
    pillLabel: 'Consolidated',
    badge: 'Consolidated query from requirements and preprocess metadata',
    showStatus: true,
    showConfirm: true,
    showGenerate: true,
  },
  response: {
    title: '5. RFP Response',
    pillLabel: 'gpt-5-chat',
    badge: 'Generated RFP response',
    showStatus: true,
  },
}

export default function AgentPanel({ agentId }) {
  const {
    pipelineData,
    updatePipelineData,
    statuses,
    updateStatus,
    confirmations,
    updateConfirmation,
    setActiveTab,
    chatSessionId,
    setChatSessionId,
    editable,
    updateEditable,
    allQuestionsAnswered,
    setAllQuestionsAnswered,
  } = usePipeline()

  const [summary, setSummary] = useState('')
  const [showChat, setShowChat] = useState(false)
  const [showPreview, setShowPreview] = useState(false)
  const [previewData, setPreviewData] = useState(null)
  const [preprocessDraft, setPreprocessDraft] = useState('')
  const [requirementsDraft, setRequirementsDraft] = useState('')
  const [buildQueryDraft, setBuildQueryDraft] = useState('')
  const [questionsGenerated, setQuestionsGenerated] = useState(false)
  
  // Auto-show chat when viewing requirements panel if session exists
  useEffect(() => {
    if (agentId === 'requirements' && chatSessionId && !showChat) {
      // Automatically show chat if we have a session but it's hidden
      setShowChat(true)
    }
  }, [agentId, chatSessionId])

  // Check if all questions are answered
  useEffect(() => {
    if (!chatSessionId || !questionsGenerated) {
      setAllQuestionsAnswered(false)
      return
    }

    let intervalId = null
    let isMounted = true

    const checkQuestionsStatus = async () => {
      if (!isMounted) return

      try {
        const sessionData = await getSession(chatSessionId)
        const questions = sessionData.questions || []
        const answers = sessionData.answers || []
        
        if (questions.length === 0) {
          // No questions means all are "answered" (nothing to answer)
          if (isMounted) {
            setAllQuestionsAnswered(true)
          }
          if (intervalId) {
            clearInterval(intervalId)
            intervalId = null
          }
          return
        }

        // Check if all questions have been answered
        const allAnswered = questions.every(q => {
          return q.answered || answers.some(a => a.question_id === q.question_id)
        })
        
        if (isMounted) {
          setAllQuestionsAnswered(allAnswered)
        }

        // Stop polling once all questions are answered
        if (allAnswered && intervalId) {
          clearInterval(intervalId)
          intervalId = null
        }
      } catch (err) {
        console.error('Failed to check questions status:', err)
        if (isMounted) {
          setAllQuestionsAnswered(false)
        }
      }
    }

    // Initial check
    checkQuestionsStatus()
    
    // Poll every 2 seconds, but stop once all questions are answered
    intervalId = setInterval(checkQuestionsStatus, 2000)
    
    return () => {
      isMounted = false
      if (intervalId) {
        clearInterval(intervalId)
      }
    }
  }, [chatSessionId, questionsGenerated])
  const config = AGENT_CONFIGS[agentId]

  // Handle build query button click
  const handleBuildQuery = async () => {
    if (!pipelineData.preprocess || !pipelineData.requirements) {
      return
    }

    try {
      updateStatus('build-query', 'processing')
      const buildQueryData = await buildQuery(pipelineData.preprocess, pipelineData.requirements)
      updatePipelineData('buildQuery', buildQueryData)
      updateStatus('build-query', 'complete')
      setSummary('Query built. Review and edit if needed, then confirm to generate questions.')
      setActiveTab('build-query')
      setQuestionsGenerated(false)
    } catch (err) {
      console.error(err)
      updateStatus('build-query', 'error')
      const errorMsg = err.message || 'Unknown error occurred'
      setSummary(`Failed to build query: ${errorMsg}`)
      
      // Provide retry option
      if (confirm(`Failed to build query: ${errorMsg}\n\nWould you like to try again?`)) {
        handleBuildQuery()
      }
    }
  }

  // Handle requirements generation
  const handleRunRequirements = async () => {
    if (!pipelineData.preprocess?.cleaned_text) {
      console.warn('Cannot run requirements: preprocess not ready', {
        hasPreprocess: !!pipelineData.preprocess,
        hasCleanedText: !!pipelineData.preprocess?.cleaned_text,
      })
      return
    }

    try {
      console.log('Starting requirements agent...')
      updateStatus('requirements', 'processing')
      setSummary('Starting requirements agent...')
      const reqData = await runRequirements(pipelineData.preprocess.cleaned_text)
      updatePipelineData('requirements', reqData)
      updateStatus('requirements', 'complete')
      let reqSummary = `Solution: ${reqData?.solution_requirements?.length || 0}, Response structure: ${reqData?.response_structure_requirements?.length || 0}`
      if (reqData?.structure_detection) {
        const sd = reqData.structure_detection
        reqSummary += ` | Structure: ${sd.has_explicit_structure ? 'EXPLICIT' : sd.structure_type.toUpperCase()} (${(sd.confidence * 100).toFixed(0)}%)`
        if (sd.detected_sections?.length > 0) {
          reqSummary += ` | Sections: ${sd.detected_sections.length}`
        }
      }
      setSummary(reqSummary)
      
      // Questions are now generated after build query, not here
    } catch (err) {
      console.error(err)
      updateStatus('requirements', 'error')
      const errorMsg = err.message || 'Unknown error occurred'
      setSummary(`Failed to run requirements agent: ${errorMsg}`)
      
      // Provide retry option
      if (confirm(`Failed to process requirements: ${errorMsg}\n\nWould you like to try again?`)) {
        handleRunRequirements()
      }
    }
  }

  // Handle preprocess editing
  const handleTogglePreprocessEdit = () => {
    if (!pipelineData.preprocess) return
    setPreprocessDraft(JSON.stringify(pipelineData.preprocess, null, 2))
    updateEditable('preprocess', !editable.preprocess)
  }

  const handleSavePreprocess = () => {
    try {
      let parsed
      try {
        parsed = JSON.parse(preprocessDraft)
      } catch (e) {
        alert('Preprocess JSON is invalid. Please fix the syntax before saving.')
        return
      }

      // Update preprocess locally
      updatePipelineData('preprocess', parsed)

      // Reset downstream steps because preprocess changed
      updatePipelineData('requirements', null)
      updatePipelineData('buildQuery', null)
      updatePipelineData('response', null)
      updateStatus('requirements', 'waiting')
      updateStatus('build-query', 'waiting')
      updateStatus('response', 'waiting')
      updateConfirmation('preprocessConfirmed', false)
      updateConfirmation('buildQueryConfirmed', false)

      updateEditable('preprocess', false)
      setSummary('Preprocess updated. Please review and confirm before running requirements.')
    } catch (err) {
      console.error('Failed to update preprocess:', err)
      alert(`Failed to update preprocess: ${err.message}`)
      updateStatus('preprocess', 'error')
    }
  }

  // Handle preview responses
  const handlePreviewResponses = async () => {
    if (!pipelineData.preprocess || !pipelineData.requirements || !confirmations.buildQueryConfirmed) {
      return
    }

    try {
      updateStatus('response', 'processing')
      setSummary('Generating responses for preview... This may take several minutes.')
      
      const previewData = await previewResponses(
        pipelineData.preprocess,
        pipelineData.requirements,
        { 
          use_rag: true, 
          num_retrieval_chunks: 5,
          session_id: chatSessionId,
        }
      )
      
      setPreviewData(previewData)
      setShowPreview(true)
      updateStatus('response', 'complete')
      setSummary(`Generated ${previewData.total} responses. Review and edit before exporting.`)
      setActiveTab('response')
    } catch (err) {
      console.error(err)
      updateStatus('response', 'error')
      setSummary(`Failed to generate preview: ${err.message}`)
    }
  }

  // Handle response generation (direct PDF)
  const handleGenerateResponse = async () => {
    if (!pipelineData.preprocess || !pipelineData.requirements || !confirmations.buildQueryConfirmed) {
      console.warn('Cannot generate response: missing data or confirmation', {
        hasPreprocess: !!pipelineData.preprocess,
        hasRequirements: !!pipelineData.requirements,
        buildQueryConfirmed: confirmations.buildQueryConfirmed
      })
      return
    }

    try {
      console.log('Starting response generation...', {
        sessionId: chatSessionId,
        useRag: true,
        numRetrievalChunks: 5
      })
      updateStatus('response', 'processing')
      setSummary('Generating response for each requirement... This may take several minutes.')
      const response = await generateResponse(
        pipelineData.preprocess,
        pipelineData.requirements,
        { 
          use_rag: true, 
          num_retrieval_chunks: 5,
          session_id: chatSessionId, // Include Q&A context if available
        }
      )
      console.log('Response generation completed:', response.type || 'json')

      if (response.type === 'pdf') {
        // Download PDF
        const url = window.URL.createObjectURL(response.blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `rfp_response_${new Date().getTime()}.pdf`
        document.body.appendChild(a)
        a.click()
        window.URL.revokeObjectURL(url)
        document.body.removeChild(a)
        const sizeKB = (response.blob.size / 1024).toFixed(1)
        setSummary(`PDF generated successfully (${sizeKB} KB)`)
        updatePipelineData('response', { type: 'pdf', size: response.blob.size })
      } else {
        updatePipelineData('response', response)
        setSummary('Response generated successfully')
      }
      updateStatus('response', 'complete')
      setActiveTab('response')
    } catch (err) {
      console.error(err)
      updateStatus('response', 'error')
      setSummary(`Failed to generate response: ${err.message}`)
    }
  }

  // Handle response editing in preview
  const handleEditResponse = async (requirementId, newText) => {
    if (!previewData) return
    
    try {
      await updateResponse(previewData.preview_id, requirementId, newText)
      // Update local state
      setPreviewData(prev => ({
        ...prev,
        responses: prev.responses.map(r => 
          r.requirement_id === requirementId 
            ? { ...r, response: newText }
            : r
        )
      }))
    } catch (err) {
      console.error('Failed to update response:', err)
      alert(`Failed to update response: ${err.message}`)
    }
  }

  // Handle export from preview
  const handleExportFromPreview = async (format = 'pdf') => {
    if (!previewData) return
    
    try {
      updateStatus('response', 'processing')
      setSummary(`Generating ${format.toUpperCase()} from preview...`)
      
      const response = await generatePDFFromPreview(
        previewData.preview_id,
        pipelineData.preprocess,
        pipelineData.requirements,
        format
      )
      
      if (response.type === 'blob') {
        const url = window.URL.createObjectURL(response.blob)
        const a = document.createElement('a')
        a.href = url
        const extension = format === 'docx' ? 'docx' : format === 'markdown' ? 'md' : 'pdf'
        a.download = `rfp_response_${new Date().getTime()}.${extension}`
        document.body.appendChild(a)
        a.click()
        window.URL.revokeObjectURL(url)
        document.body.removeChild(a)
        const sizeKB = (response.blob.size / 1024).toFixed(1)
        setSummary(`${format.toUpperCase()} exported successfully (${sizeKB} KB)`)
        setShowPreview(false)
      }
    } catch (err) {
      console.error(err)
      alert(`Failed to export ${format.toUpperCase()}: ${err.message}`)
    } finally {
      updateStatus('response', 'complete')
    }
  }

  // Get content for display
  const getContent = () => {
    switch (agentId) {
      case 'ocr':
        return pipelineData.ocr || 'Waiting for OCR…'
      case 'preprocess':
        return pipelineData.preprocess ? formatPreprocessOutput(pipelineData.preprocess) : 'Processing...'
      case 'requirements':
        let reqOutput = pipelineData.requirements ? formatRequirementsOutput(pipelineData.requirements) : 'Processing...'
        // Add structure detection info if available
        if (pipelineData.requirements?.structure_detection) {
          const sd = pipelineData.requirements.structure_detection
          reqOutput += "\n\n" + "=".repeat(60) + "\n"
          reqOutput += "STRUCTURE DETECTION\n"
          reqOutput += "=".repeat(60) + "\n\n"
          reqOutput += `Explicit Structure: ${sd.has_explicit_structure ? 'YES' : 'NO'}\n`
          reqOutput += `Structure Type: ${sd.structure_type}\n`
          reqOutput += `Confidence: ${(sd.confidence * 100).toFixed(1)}%\n`
          if (sd.detected_sections && sd.detected_sections.length > 0) {
            reqOutput += `Detected Sections (${sd.detected_sections.length}):\n`
            sd.detected_sections.forEach((section, idx) => {
              reqOutput += `  ${idx + 1}. ${section}\n`
            })
          }
          reqOutput += `\nDescription: ${sd.structure_description}\n`
        }
        return reqOutput
      case 'build-query':
        return pipelineData.buildQuery?.query_text || 'Build query will appear here after requirements are processed...'
      case 'response':
        if (!confirmations.buildQueryConfirmed) {
          return 'Confirm build query to generate response...'
        }
        if (pipelineData.response) {
          // If we generated a PDF (or other non-text blob), show a clear completion message
          if (pipelineData.response.type === 'pdf') {
            const sizeKB = (pipelineData.response.size / 1024).toFixed(1)
            return `PDF generated successfully (${sizeKB} KB). Check your downloads.`
          }
          // Fallback to any response text we have
          if (pipelineData.response.response_text) {
            return pipelineData.response.response_text
          }
          // Generic success message if response exists but has no text field
          return 'Response generated successfully.'
        }
        return 'Generating response...'
      default:
        return 'Waiting...'
    }
  }

  // Get summary text
  const getSummaryText = () => {
    if (summary) return summary

    switch (agentId) {
      case 'preprocess':
        if (pipelineData.preprocess) {
          const pp = pipelineData.preprocess
          const base = `Language: ${pp.language || 'unknown'}, Cleaned: ${pp.cleaned_text?.length || 0} chars`
          return confirmations.preprocessConfirmed
            ? `${base} (confirmed)`
            : base
        }
        return 'Waiting...'
      case 'requirements':
        if (pipelineData.requirements) {
          const req = pipelineData.requirements
          let summary = `Solution: ${req.solution_requirements?.length || 0}, Response structure: ${req.response_structure_requirements?.length || 0}`
          if (req.structure_detection) {
            const sd = req.structure_detection
            summary += ` | Structure: ${sd.has_explicit_structure ? 'EXPLICIT' : sd.structure_type.toUpperCase()} (${(sd.confidence * 100).toFixed(0)}%)`
            if (sd.detected_sections?.length > 0) {
              summary += ` | Sections: ${sd.detected_sections.length}`
            }
          }
          return summary
        }
        return 'Processing...'
      case 'build-query':
        return pipelineData.buildQuery ? 'Query built. Please review, edit if needed, and confirm to generate questions.' : 'Waiting...'
      case 'response':
        if (pipelineData.response) {
          return pipelineData.response.type === 'pdf' 
            ? `PDF generated successfully (${(pipelineData.response.size / 1024).toFixed(1)} KB)`
            : 'Response generated successfully'
        }
        return 'Waiting...'
      default:
        return ''
    }
  }

  const status = statuses[agentId] || 'waiting'
  const content = getContent()
  const summaryText = getSummaryText()
  
  // Start iterative question flow - creates session and lets ChatInterface handle the rest
  const handleGenerateQuestionsOnce = async () => {
    if (!pipelineData.buildQuery || !pipelineData.requirements || questionsGenerated) {
      return
    }

    try {
      console.log('Starting iterative question flow...')
      setSummary('Searching RAG for existing information...')
      
      // Create a session - the ChatInterface will use iterative mode to get questions one at a time
      const sessionData = await createChatSession()
      setChatSessionId(sessionData.session_id)
      console.log('Session created:', sessionData.session_id)
      
      // The ChatInterface with iterativeMode=true will call getNextQuestion on mount
      // and handle the one-at-a-time flow
      setAllQuestionsAnswered(false)
      setSummary('Query confirmed. Check the Q&A panel for any critical questions.')
      
    } catch (err) {
      console.error('Failed to start question flow:', err)
      setSummary('Query confirmed. (Question check failed - you can still proceed)')
      setAllQuestionsAnswered(true)
    } finally {
      setQuestionsGenerated(true)
    }
  }

  const handleToggleRequirementsEdit = () => {
    if (!pipelineData.requirements) return
    setRequirementsDraft(JSON.stringify(pipelineData.requirements, null, 2))
    updateEditable('requirements', !editable.requirements)
  }

  const handleSaveRequirements = async () => {
    try {
      let parsed
      try {
        parsed = JSON.parse(requirementsDraft)
      } catch (e) {
        alert('Requirements JSON is invalid. Please fix the syntax before saving.')
        return
      }
      updateStatus('requirements', 'processing')
      const updated = await updateRequirements(parsed)
      updatePipelineData('requirements', updated)
      updateStatus('requirements', 'complete')
      updateEditable('requirements', false)
    } catch (err) {
      console.error('Failed to update requirements:', err)
      alert(`Failed to update requirements: ${err.message}`)
      updateStatus('requirements', 'error')
    }
  }

  const handleToggleBuildQueryEdit = () => {
    if (!pipelineData.buildQuery?.query_text) return
    setBuildQueryDraft(pipelineData.buildQuery.query_text)
    updateEditable('buildQuery', !editable.buildQuery)
  }

  const handleSaveBuildQuery = () => {
    if (!pipelineData.buildQuery) return
    // Update build query text locally; no backend call needed
    updatePipelineData('buildQuery', {
      ...pipelineData.buildQuery,
      query_text: buildQueryDraft,
    })
    // Reset confirmation and questions so they are regenerated for the edited query
    updateConfirmation('buildQueryConfirmed', false)
    setQuestionsGenerated(false)
    updateEditable('buildQuery', false)
    setSummary('Build query updated. Please confirm again to generate questions.')
  }

  return (
    <div className="agent-panel">
      <div className="agent-header">
        <h2>{config.title}</h2>
        {config.showStatus && config.pillLabel && (
          <StatusPill status={status} label={config.pillLabel} />
        )}
      </div>
      
      {config.description && (
        <div className="agent-summary">
          <strong>Description:</strong> {config.description}
        </div>
      )}
      
      {config.showStatus && (
        <div className="agent-summary">
          <strong>Status:</strong> {status === 'processing' ? 'Processing...' : status === 'complete' ? 'Complete' : status === 'error' ? 'Error' : 'Waiting...'}
          {summaryText && <><br /><strong>Summary:</strong> {summaryText}</>}
        </div>
      )}
      
      {config.badge && (
        <div className="badge">{config.badge}</div>
      )}
     
      {/* Scope / Requirements / Build Query editable views */}
      {agentId === 'preprocess' && editable.preprocess && pipelineData.preprocess ? (
        <div className="editable-section">
          <label className="edit-label">
            Edit preprocess JSON before running requirements:
          </label>
          <textarea
            className="edit-textarea"
            value={preprocessDraft}
            onChange={(e) => setPreprocessDraft(e.target.value)}
            rows={20}
          />
          <div className="edit-actions">
            <Button onClick={handleSavePreprocess} disabled={status === 'processing'}>
              Save preprocess
            </Button>
            <Button variant="secondary" onClick={handleTogglePreprocessEdit}>
              Cancel
            </Button>
          </div>
        </div>
      ) : agentId === 'requirements' && editable.requirements && pipelineData.requirements ? (
        <div className="editable-section">
          <label className="edit-label">
            Edit requirements JSON before building query:
          </label>
          <textarea
            className="edit-textarea"
            value={requirementsDraft}
            onChange={(e) => setRequirementsDraft(e.target.value)}
            rows={20}
          />
          <div className="edit-actions">
            <Button onClick={handleSaveRequirements} disabled={status === 'processing'}>
              Save requirements
            </Button>
            <Button variant="secondary" onClick={handleToggleRequirementsEdit}>
              Cancel
            </Button>
          </div>
        </div>
      ) : agentId === 'build-query' && editable.buildQuery && pipelineData.buildQuery ? (
        <div className="editable-section">
          <label className="edit-label">
            Edit build query before confirming:
          </label>
          <textarea
            className="edit-textarea"
            value={buildQueryDraft}
            onChange={(e) => setBuildQueryDraft(e.target.value)}
            rows={16}
          />
          <div className="edit-actions">
            <Button onClick={handleSaveBuildQuery} disabled={status === 'processing'}>
              Save build query
            </Button>
            <Button variant="secondary" onClick={handleToggleBuildQueryEdit}>
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <OutputDisplay content={content} />
      )}

      {/* Preprocess confirm + edit actions */}
      {agentId === 'preprocess' && pipelineData.preprocess && (
        <div className="accept-row">
          <Button
            onClick={async () => {
              console.log('Confirm preprocess clicked', {
                currentState: confirmations.preprocessConfirmed,
                requirementsStatus: statuses.requirements,
              })
              
              // Set flag to allow requirements to run
              updateConfirmation('preprocessConfirmed', true)
              console.log('Preprocess confirmed - automatically starting requirements agent...')
              
              // Automatically trigger requirements agent
              await handleRunRequirements()
            }}
            className={
              statuses.requirements === 'processing' || statuses.requirements === 'complete'
                ? 'accepted'
                : ''
            }
            disabled={
              status === 'processing' || 
              statuses.requirements === 'processing' || 
              statuses.requirements === 'complete'
            }
          >
            {statuses.requirements === 'processing' || statuses.requirements === 'complete'
              ? '✓ Preprocess confirmed'
              : statuses.requirements === 'error'
              ? 'Retry requirements'
              : 'Confirm preprocess'}
          </Button>
          <Button
            variant="secondary"
            onClick={handleTogglePreprocessEdit}
            style={{ marginLeft: '0.5rem' }}
            disabled={statuses.requirements === 'processing' || statuses.requirements === 'complete'}
          >
            {editable.preprocess ? 'Close editor' : 'Edit preprocess JSON'}
          </Button>
        </div>
      )}

      {config.showBuildQuery && agentId === 'requirements' && pipelineData.requirements && (
        <div className="accept-row">
          {chatSessionId && showChat && (
            <div style={{ 
              marginBottom: '1rem', 
              padding: '0.75rem', 
              background: 'rgba(37, 99, 235, 0.1)', 
              border: '1px solid rgba(37, 99, 235, 0.3)', 
              borderRadius: '0.5rem',
              color: '#60a5fa'
            }}>
              ⚠️ <strong>Questions available below!</strong> Please answer them before building the query to improve response quality.
            </div>
          )}
          <Button onClick={handleBuildQuery} disabled={status === 'processing' || editable.requirements}>
            Build Query
          </Button>
          <Button
            variant="secondary"
            onClick={handleToggleRequirementsEdit}
            style={{ marginLeft: '0.5rem' }}
          >
            {editable.requirements ? 'Close editor' : 'Edit requirements JSON'}
          </Button>
        </div>
      )}
      
      {agentId === 'build-query' && pipelineData.buildQuery && (
        <>
          {!questionsGenerated && (
            <div className="accept-row" style={{ marginTop: '0.5rem' }}>
              <Button onClick={handleGenerateQuestionsOnce} disabled={status === 'processing'}>
                Confirm & generate questions
              </Button>
              <Button
                variant="secondary"
                onClick={handleToggleBuildQueryEdit}
              >
                {editable.buildQuery ? 'Close editor' : 'Edit build query'}
              </Button>
            </div>
          )}

          {questionsGenerated && allQuestionsAnswered && (
            <div className="accept-row" style={{ marginTop: '0.5rem', display: 'flex', gap: '0.5rem' }}>
              <Button
                onClick={() => updateConfirmation('buildQueryConfirmed', !confirmations.buildQueryConfirmed)}
                className={confirmations.buildQueryConfirmed ? 'accepted' : ''}
              >
                {confirmations.buildQueryConfirmed ? '✓ Build query confirmed' : 'Confirm build query'}
              </Button>
              <Button
                variant="secondary"
                onClick={handleToggleBuildQueryEdit}
              >
                {editable.buildQuery ? 'Close editor' : 'Edit build query'}
              </Button>
            </div>
          )}
          
          {questionsGenerated && !allQuestionsAnswered && chatSessionId && (
            <div className="accept-row" style={{ marginTop: '0.5rem', padding: '0.75rem', background: 'rgba(37, 99, 235, 0.1)', border: '1px solid rgba(37, 99, 235, 0.3)', borderRadius: '0.5rem', color: '#60a5fa' }}>
              Please answer all questions in the chat panel before confirming the build query.
            </div>
          )}
        </>
      )}
      
      {config.showGenerate && agentId === 'build-query' && confirmations.buildQueryConfirmed && questionsGenerated && allQuestionsAnswered && (
        <div className="accept-row" style={{ marginTop: '0.5rem', display: 'flex', gap: '0.5rem' }}>
          <Button onClick={handlePreviewResponses} disabled={status === 'processing'}>
            Preview Responses
          </Button>
          <Button onClick={handleGenerateResponse} disabled={status === 'processing'}>
            Generate PDF Directly
          </Button>
        </div>
      )}
      
      {/* Chat is now in fixed sidebar - removed from here */}
      
      {showPreview && previewData && (
        <ResponsePreview
          responses={previewData.responses}
          onEdit={handleEditResponse}
          onExport={handleExportFromPreview}
          onClose={() => setShowPreview(false)}
        />
      )}
    </div>
  )
}

