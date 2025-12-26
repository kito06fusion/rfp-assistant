import React, { useState, useEffect, useRef } from 'react'
import mammoth from 'mammoth'
import Button from './Button'
import './DocumentViewer.css'

// Helper function to sanitize filename by removing invalid characters
const sanitizeFilename = (filename) => {
  if (!filename) return ''
  // Remove invalid characters for filenames: / \ : * ? " < > | and spaces
  return filename.replace(/[\/\\:*?"<>|\s]/g, '').trim()
}

// Validate filename requirements
const validateFilename = (filename) => {
  if (!filename || filename.trim() === '') {
    return { valid: true, error: null } // Empty is OK (will use default)
  }
  
  // Remove .docx extension if present for validation
  const nameWithoutExt = filename.replace(/\.docx$/i, '')
  
  if (nameWithoutExt.length === 0) {
    return { valid: false, error: 'Filename cannot be empty' }
  }
  
  // Must contain at least one letter
  if (!/[a-zA-Z]/.test(nameWithoutExt)) {
    return { valid: false, error: 'Filename must contain at least one letter' }
  }
  
  // Cannot contain spaces
  if (/\s/.test(nameWithoutExt)) {
    return { valid: false, error: 'Filename cannot contain spaces' }
  }
  
  // Cannot contain invalid characters
  if (/[\/\\:*?"<>|]/.test(nameWithoutExt)) {
    return { valid: false, error: 'Filename contains invalid characters' }
  }
  
  return { valid: true, error: null }
}

export default function DocumentViewer({ docxBlob, onSave, onClose }) {
  const [htmlContent, setHtmlContent] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [isSaving, setIsSaving] = useState(false)
  const [filename, setFilename] = useState('')
  const [filenameError, setFilenameError] = useState(null)
  const contentRef = useRef(null)

  useEffect(() => {
    if (!docxBlob) {
      setLoading(false)
      return
    }

    setLoading(true)
    setError(null)

    docxBlob.arrayBuffer()
      .then((arrayBuffer) => {
        return mammoth.convertToHtml({ arrayBuffer })
      })
      .then((result) => {
        setHtmlContent(result.value)
        setLoading(false)
      })
      .catch((err) => {
        console.error('Failed to convert DOCX to HTML:', err)
        setError('Failed to load document. Please try again.')
        setLoading(false)
      })
  }, [docxBlob])

  const handleSave = async () => {
    if (!onSave) return

    // Validate filename if provided
    if (filename.trim()) {
      const validation = validateFilename(filename)
      if (!validation.valid) {
        setFilenameError(validation.error)
        return
      }
    }

    setIsSaving(true)
    setFilenameError(null)
    try {
      // Get the edited HTML content from the contentEditable div
      const editedHtml = contentRef.current?.innerHTML || htmlContent
      
      // Sanitize filename before saving (remove spaces and invalid chars)
      const sanitizedFilename = filename.trim() 
        ? sanitizeFilename(filename.trim()) 
        : null
      
      // Validate again after sanitization
      if (sanitizedFilename) {
        const validation = validateFilename(sanitizedFilename)
        if (!validation.valid) {
          setFilenameError(validation.error)
          setIsSaving(false)
          return
        }
      }
      
      // Send the edited HTML content to the backend for conversion to DOCX
      // Pass the filename if provided
      await onSave(null, editedHtml, sanitizedFilename || null)
      setIsSaving(false)
    } catch (err) {
      console.error('Failed to save document:', err)
      setError('Failed to save document. Please try again.')
      setIsSaving(false)
    }
  }

  const handleDownload = () => {
    if (!docxBlob) return
    
    // Validate filename if provided
    if (filename.trim()) {
      const validation = validateFilename(filename)
      if (!validation.valid) {
        setFilenameError(validation.error)
        return
      }
    }
    
    const url = window.URL.createObjectURL(docxBlob)
    const a = document.createElement('a')
    a.href = url
    // Use custom filename if provided, otherwise use default
    // Sanitize filename before using it (remove spaces and invalid chars)
    const sanitizedFilename = filename.trim() ? sanitizeFilename(filename.trim()) : ''
    
    // Validate again after sanitization
    if (sanitizedFilename) {
      const validation = validateFilename(sanitizedFilename)
      if (!validation.valid) {
        setFilenameError(validation.error)
        window.URL.revokeObjectURL(url)
        return
      }
    }
    
    const downloadFilename = sanitizedFilename
      ? (sanitizedFilename.endsWith('.docx') ? sanitizedFilename : `${sanitizedFilename}.docx`)
      : `rfp_response_${new Date().getTime()}.docx`
    a.download = downloadFilename
    document.body.appendChild(a)
    a.click()
    window.URL.revokeObjectURL(url)
    document.body.removeChild(a)
    setFilenameError(null)
  }

  const handleFilenameChange = (e) => {
    let newValue = e.target.value
    
    // Automatically remove spaces as user types
    if (newValue.includes(' ')) {
      newValue = newValue.replace(/\s/g, '')
    }
    
    setFilename(newValue)
    
    // Clear error when user starts typing
    if (filenameError) {
      setFilenameError(null)
    }
    
    // Real-time validation feedback
    if (newValue.trim()) {
      const validation = validateFilename(newValue)
      if (!validation.valid) {
        setFilenameError(validation.error)
      } else {
        setFilenameError(null)
      }
    } else {
      setFilenameError(null)
    }
  }

  if (loading) {
    return (
      <div className="document-viewer">
        <div className="document-viewer-header">
          <h2>Document Viewer</h2>
          {onClose && (
            <button className="close-btn" onClick={onClose}>×</button>
          )}
        </div>
        <div className="document-viewer-loading">
          <p>Loading document...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="document-viewer">
        <div className="document-viewer-header">
          <h2>Document Viewer</h2>
          {onClose && (
            <button className="close-btn" onClick={onClose}>×</button>
          )}
        </div>
        <div className="document-viewer-error">
          <p>{error}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="document-viewer">
      <div className="document-viewer-header">
        <h2>RFP Response Document</h2>
        <div className="document-viewer-actions">
          <div className="filename-input-group">
            <label htmlFor="filename-input" className="filename-label">Filename:</label>
            <div className="filename-input-wrapper">
              <input
                id="filename-input"
                type="text"
                className={`filename-input ${filenameError ? 'filename-input-error' : ''}`}
                value={filename}
                onChange={handleFilenameChange}
                placeholder="Choose your filename"
              />
              {filenameError && (
                <span className="filename-error-message">{filenameError}</span>
              )}
            </div>
          </div>
          <Button 
            onClick={handleDownload}
            variant="secondary"
            disabled={!docxBlob || (filename.trim() && filenameError)}
          >
            Download
          </Button>
          {onSave && (
            <Button 
              onClick={handleSave}
              disabled={!docxBlob || isSaving || (filename.trim() && filenameError)}
            >
              {isSaving ? 'Saving...' : 'Save to Output Folder'}
            </Button>
          )}
          {onClose && (
            <button className="close-btn" onClick={onClose}>×</button>
          )}
        </div>
      </div>
      <div 
        ref={contentRef}
        className="document-viewer-content"
        contentEditable={true}
        suppressContentEditableWarning={true}
        dangerouslySetInnerHTML={{ __html: htmlContent }}
      />
    </div>
  )
}

