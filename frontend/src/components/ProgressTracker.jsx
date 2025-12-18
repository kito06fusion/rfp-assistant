import React from 'react'
import { usePipeline } from '../context/PipelineContext'
import './ProgressTracker.css'

const PIPELINE_STEPS = [
  { id: 'ocr', label: 'OCR', order: 1 },
  { id: 'preprocess', label: 'Preprocess', order: 2 },
  { id: 'requirements', label: 'Requirements', order: 3 },
  { id: 'build-query', label: 'Build Query', order: 4 },
  { id: 'response', label: 'Response', order: 5 },
]

export default function ProgressTracker() {
  const { statuses, confirmations, pipelineData } = usePipeline()

  const getStepStatus = (stepId) => {
    const status = statuses[stepId] || 'waiting'
    
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
      if (status === 'waiting' && status !== 'blocked') {
        return step
      }
    }
    return null
  }

  const progress = calculateProgress()
  const currentStep = getCurrentStep()

  return (
    <div className="progress-tracker">
      <div className="progress-header">
        <h3>Pipeline Progress</h3>
        <div className="progress-percentage">{progress}%</div>
      </div>
      
      <div className="progress-bar-container">
        <div 
          className="progress-bar-fill" 
          style={{ width: `${progress}%` }}
        />
      </div>
      
      <div className="progress-steps">
        {PIPELINE_STEPS.map((step, index) => {
          const stepStatus = getStepStatus(step.id)
          const isActive = currentStep?.id === step.id
          
          return (
            <div 
              key={step.id} 
              className={`progress-step progress-step-${stepStatus} ${isActive ? 'active' : ''}`}
            >
              <div className="step-indicator">
                {stepStatus === 'complete' && <span className="step-check">✓</span>}
                {stepStatus === 'processing' && <span className="step-spinner">⟳</span>}
                {stepStatus === 'error' && <span className="step-error">✗</span>}
                {stepStatus === 'blocked' && <span className="step-blocked">⊘</span>}
                {(stepStatus === 'waiting' && !isActive) && <span className="step-number">{step.order}</span>}
                {isActive && stepStatus === 'waiting' && <span className="step-number">{step.order}</span>}
              </div>
              <div className="step-label">{step.label}</div>
            </div>
          )
        })}
      </div>
      
      {currentStep && statuses[currentStep.id] === 'processing' && (
        <div className="progress-status">
          Processing {currentStep.label}...
        </div>
      )}
    </div>
  )
}

