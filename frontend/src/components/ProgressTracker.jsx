import React from 'react'
import { usePipeline } from '../context/PipelineContext'
import './ProgressTracker.css'

const PIPELINE_STEPS = [
  { id: 'ocr', label: 'Extract Text', description: 'OCR', order: 1 },
  { id: 'preprocess', label: 'Preprocess', description: 'Preprocess', order: 2 },
  { id: 'requirements', label: 'Identify Requirements', description: 'Requirements', order: 3 },
  { id: 'build-query', label: 'Build Query', description: 'Build Query', order: 4 },
  { id: 'response', label: 'Generate Response', description: 'Response', order: 5 },
]

export default function ProgressTracker() {
  const { statuses, confirmations, pipelineData } = usePipeline()

  const getStepStatus = (stepId) => {
    const status = statuses[stepId] || 'waiting'
    
    // Special handling for OCR: if OCR data exists, it's complete
    if (stepId === 'ocr') {
      if (pipelineData.ocr) {
        return 'complete'
      }
      return status
    }
    
    // Preprocess must be confirmed before moving to requirements
    if (stepId === 'requirements' && !confirmations.preprocessConfirmed && status === 'waiting') {
      return 'blocked'
    }
    
    // Special handling for build-query (needs requirements)
    if (stepId === 'build-query' && !pipelineData.requirements && status === 'waiting') {
      return 'blocked'
    }
    
    // Special handling for response (needs build query confirmation)
    if (stepId === 'response' && !confirmations.buildQueryConfirmed && status === 'waiting') {
      return 'blocked'
    }
    // If an explicit error state has been set, keep it
    if (status === 'error') return 'error'

    // If pipeline data for a step exists, prefer marking it complete
    // unless an explicit error state was set above.
    if (stepId === 'ocr' && pipelineData.ocr) return 'complete'
    if (stepId === 'preprocess' && pipelineData.preprocess) return 'complete'
    if (stepId === 'requirements' && pipelineData.requirements) return 'complete'
    if (stepId === 'build-query' && pipelineData.buildQuery) return 'complete'
    if (stepId === 'response' && pipelineData.response) return 'complete'

    return status
  }

  const calculateProgress = () => {
    let completed = 0
    let total = PIPELINE_STEPS.length
    
    PIPELINE_STEPS.forEach(step => {
      const stepStatus = getStepStatus(step.id)
      if (stepStatus === 'complete') {
        completed++
      }
    })
    
    return Math.round((completed / total) * 100)
  }

  const getCurrentStep = () => {
    for (const step of PIPELINE_STEPS) {
      const status = getStepStatus(step.id)
      if (status === 'processing') {
        return step
      }
      if (status === 'waiting') {
        return step
      }
    }
    return null
  }

  const progress = calculateProgress()
  const currentStep = getCurrentStep()
  const currentStepIndex = currentStep ? PIPELINE_STEPS.findIndex(s => s.id === currentStep.id) : -1
  const totalSteps = PIPELINE_STEPS.length

  const getStatusText = () => {
    if (statuses['response'] === 'error' || getStepStatus('response') === 'error') {
      return 'Error generating response'
    }
    if (statuses['response'] === 'processing' || getStepStatus('response') === 'processing') {
      return 'Generating response'
    }
    if (getStepStatus('response') === 'complete') {
      return 'Response generated'
    }
    if (currentStep && getStepStatus(currentStep.id) === 'processing') {
      return currentStep.label
    }
    if (progress === 0) {
      return 'Waiting for upload'
    }
    return ''
  }

  return (
    <div className="progress-tracker" role="region" aria-label="Pipeline progress">
      <div className="progress-header">
        <h3>Pipeline Progress</h3>
        <div className="progress-percentage-wrapper">
          <span className="progress-percentage">{progress}%</span>
          {progress === 0 && <span className="progress-context">• Waiting for upload</span>}
        </div>
      </div>
      
      <div className="progress-bar-container" role="progressbar" aria-valuenow={progress} aria-valuemin="0" aria-valuemax="100" aria-label="Overall progress">
        <div 
          className="progress-bar-fill" 
          style={{ width: `${progress}%` }}
        />
      </div>
      
      <div className="progress-steps" role="list">
        {PIPELINE_STEPS.map((step, index) => {
          const stepStatus = getStepStatus(step.id)
          const isActive = currentStep?.id === step.id
          const isComplete = stepStatus === 'complete'
          
          return (
            <div 
              key={step.id} 
              className={`progress-step progress-step-${stepStatus} ${isActive ? 'active' : ''}`}
              role="listitem"
              aria-label={`Step ${step.order}: ${step.label} - ${stepStatus === 'complete' ? 'Complete' : stepStatus === 'processing' ? 'Processing' : stepStatus === 'error' ? 'Error' : 'Waiting'}`}
            >
              <div className="step-indicator" aria-hidden="true">
                {isComplete && <span className="step-check">✓</span>}
                {stepStatus === 'processing' && <span className="step-spinner"></span>}
                {stepStatus === 'error' && <span className="step-error">✗</span>}
                {stepStatus === 'blocked' && <span className="step-blocked">⊘</span>}
                {stepStatus === 'waiting' && <span className="step-number">{step.order}</span>}
              </div>
              <div className="step-content">
                <div className="step-label">{step.label}</div>
                {isActive && stepStatus === 'processing' && (
                  <div className="step-description">Processing...</div>
                )}
                {isActive && stepStatus === 'waiting' && (
                  <div className="step-description">Ready to start</div>
                )}
              </div>
            </div>
          )
        })}
      </div>
      
      {getStatusText() && (
        <div className="progress-status" role="status" aria-live="polite">
          {getStatusText()}
        </div>
      )}
    </div>
  )
}

