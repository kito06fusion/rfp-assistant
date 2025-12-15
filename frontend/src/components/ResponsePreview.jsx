import React, { useState } from 'react'
import './ResponsePreview.css'

export default function ResponsePreview({ responses, onEdit, onExport, onClose }) {
  const [editingId, setEditingId] = useState(null)
  const [editedResponses, setEditedResponses] = useState({})
  const [showDiff, setShowDiff] = useState({})

  const handleEdit = (responseId, originalText) => {
    setEditingId(responseId)
    if (!editedResponses[responseId]) {
      setEditedResponses(prev => ({ ...prev, [responseId]: originalText }))
    }
  }

  const handleSave = (responseId) => {
    setEditingId(null)
    if (onEdit && editedResponses[responseId]) {
      onEdit(responseId, editedResponses[responseId])
    }
  }

  const handleCancel = (responseId, originalText) => {
    setEditingId(null)
    setEditedResponses(prev => {
      const newState = { ...prev }
      delete newState[responseId]
      return newState
    })
    setShowDiff(prev => {
      const newState = { ...prev }
      delete newState[responseId]
      return newState
    })
  }

  const toggleDiff = (responseId, originalText) => {
    setShowDiff(prev => ({
      ...prev,
      [responseId]: !prev[responseId]
    }))
  }

  return (
    <div className="response-preview-overlay">
      <div className="response-preview-modal">
        <div className="preview-header">
          <h2>Response Preview</h2>
          <div className="preview-actions">
            <select className="export-format-select" id="export-format" defaultValue="pdf">
              <option value="pdf">PDF</option>
              <option value="docx">DOCX</option>
              <option value="markdown">Markdown</option>
            </select>
            <button className="export-btn" onClick={() => {
              const format = document.getElementById('export-format').value
              onExport(format)
            }}>
              Export
            </button>
            {onClose && (
              <button className="close-btn" onClick={onClose}>×</button>
            )}
          </div>
        </div>
        
        <div className="preview-content">
          {responses && responses.length > 0 ? (
            responses.map((resp, idx) => {
              const isEditing = editingId === resp.requirement_id
              const editedText = editedResponses[resp.requirement_id] || resp.response
              const hasEdits = editedResponses[resp.requirement_id] && 
                              editedResponses[resp.requirement_id] !== resp.response
              
              return (
                <div key={resp.requirement_id || idx} className="preview-item">
                  <div className="preview-item-header">
                    <div>
                      <h3>Requirement {idx + 1}: {resp.requirement_id}</h3>
                      {resp.quality && (
                        <div className="quality-indicator">
                          <span className={`quality-score quality-${resp.quality.completeness}`}>
                            Quality: {resp.quality.score.toFixed(0)}/100
                          </span>
                          <span className={`quality-badge quality-${resp.quality.completeness}`}>
                            {resp.quality.completeness}
                          </span>
                          <span className={`quality-badge quality-${resp.quality.relevance}`}>
                            {resp.quality.relevance} relevance
                          </span>
                        </div>
                      )}
                    </div>
                    <div className="item-actions">
                      {hasEdits && (
                        <button 
                          className="diff-btn"
                          onClick={() => toggleDiff(resp.requirement_id, resp.response)}
                        >
                          {showDiff[resp.requirement_id] ? 'Hide' : 'Show'} Diff
                        </button>
                      )}
                      {!isEditing ? (
                        <button 
                          className="edit-btn"
                          onClick={() => handleEdit(resp.requirement_id, resp.response)}
                        >
                          Edit
                        </button>
                      ) : (
                        <>
                          <button 
                            className="save-btn"
                            onClick={() => handleSave(resp.requirement_id)}
                          >
                            Save
                          </button>
                          <button 
                            className="cancel-btn"
                            onClick={() => handleCancel(resp.requirement_id, resp.response)}
                          >
                            Cancel
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                  
                  <div className="preview-item-content">
                    {showDiff[resp.requirement_id] && hasEdits ? (
                      <div className="diff-view">
                        <div className="diff-original">
                          <h4>Original:</h4>
                          <pre>{resp.response}</pre>
                        </div>
                        <div className="diff-edited">
                          <h4>Edited:</h4>
                          <pre>{editedText}</pre>
                        </div>
                      </div>
                    ) : isEditing ? (
                      <textarea
                        className="edit-textarea"
                        value={editedText}
                        onChange={(e) => setEditedResponses(prev => ({
                          ...prev,
                          [resp.requirement_id]: e.target.value
                        }))}
                        rows={15}
                      />
                    ) : (
                      <div className="response-text">
                        {hasEdits ? (
                          <>
                            <span className="edited-badge">Edited</span>
                            <pre>{editedText}</pre>
                          </>
                        ) : (
                          <pre>{resp.response}</pre>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )
            })
          ) : (
            <div className="preview-empty">
              <p>No responses to preview</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

