import React, { useState, useRef } from 'react'
import { usePipeline } from '../context/PipelineContext'
import { processRFP } from '../services/api'
import './UploadSection.css'

export default function UploadSection() {
  const { updatePipelineData, updateStatus, resetPipeline, pipelineData } = usePipeline()
  const [files, setFiles] = useState([])
  const [status, setStatus] = useState('')
  const [isProcessing, setIsProcessing] = useState(false)
  const [isDragging, setIsDragging] = useState(false)
  const fileInputRef = useRef(null)
  const dropZoneRef = useRef(null)
  
  // Hide upload section after OCR is complete
  if (pipelineData.ocr) {
    return null
  }

  const handleFileSelect = (selectedFiles) => {
    const fileArray = Array.from(selectedFiles)
    setFiles(fileArray)
    if (fileArray.length > 0) {
      setStatus('')
    }
  }

  const handleFileChange = (e) => {
    handleFileSelect(e.target.files)
  }

  const handleDragOver = (e) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(true)
  }

  const handleDragLeave = (e) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
  }

  const handleDrop = (e) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
    
    const droppedFiles = e.dataTransfer.files
    if (droppedFiles.length > 0) {
      handleFileSelect(droppedFiles)
    }
  }

  const handleClick = () => {
    fileInputRef.current?.click()
  }

  const handleRemoveFile = (e) => {
    e.stopPropagation()
    setFiles([])
    setStatus('')
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 Bytes'
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i]
  }

  const handleUpload = async () => {
    if (files.length === 0) {
      setStatus('Please select a file to continue.')
      return
    }

    setIsProcessing(true)
    resetPipeline()
    updateStatus('ocr', 'processing')
    const fileCount = files.length
    setStatus(`Uploading ${fileCount} file${fileCount > 1 ? 's' : ''} and extracting text…`)

    try {
      const data = await processRFP(files)
      // Store the first filename for display in header
      const fileName = files[0]?.name || 'RFP Document'
      updatePipelineData('ocr', data.ocr_source_text || 'No OCR text returned.')
      updatePipelineData('uploadedFileName', fileName)
      updatePipelineData('preprocess', null)
      updateStatus('ocr', 'complete')
      updateStatus('preprocess', 'waiting')
      setStatus('OCR extraction finished. Please review and confirm the OCR text to proceed.')
    } catch (err) {
      console.error(err)
      setStatus(`Failed to process files: ${err.message}`)
      updateStatus('ocr', 'error')
      updateStatus('preprocess', 'error')
    } finally {
      setIsProcessing(false)
    }
  }

  const hasFiles = files.length > 0
  const totalSize = files.reduce((sum, file) => sum + file.size, 0)

  return (
    <section className="upload-card">
      <div 
        ref={dropZoneRef}
        className={`upload-dropzone ${isDragging ? 'dragging' : ''} ${hasFiles ? 'has-files' : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={!hasFiles ? handleClick : undefined}
        role="button"
        tabIndex={0}
        aria-label="Upload RFP file"
        onKeyDown={(e) => {
          if ((e.key === 'Enter' || e.key === ' ') && !hasFiles) {
            e.preventDefault()
            handleClick()
          }
        }}
      >
        <input
          ref={fileInputRef}
          id="file-input"
          type="file"
          accept=".pdf,.doc,.docx,.xls,.xlsx,.txt"
          onChange={handleFileChange}
          disabled={isProcessing}
          multiple
          aria-label="Select RFP file"
          style={{ display: 'none' }}
        />
        
        {!hasFiles ? (
          <>
            <div className="upload-icon">📄</div>
            <h2 className="upload-headline">Upload an RFP</h2>
            <p className="upload-description">
              Accepted formats: PDF, DOC, DOCX, XLS, XLSX, TXT
            </p>
            <button
              className="upload-browse-btn"
              onClick={(e) => {
                e.stopPropagation()
                handleClick()
              }}
              disabled={isProcessing}
            >
              Browse Files
            </button>
          </>
        ) : (
          <div className="upload-file-list">
            {files.map((file, index) => (
              <div key={index} className="upload-file-item">
                <div className="upload-file-info">
                  <span className="upload-file-name">{file.name}</span>
                  <span className="upload-file-size">{formatFileSize(file.size)}</span>
                </div>
                <button
                  className="upload-file-remove"
                  onClick={handleRemoveFile}
                  disabled={isProcessing}
                  aria-label={`Remove ${file.name}`}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="upload-actions">
        <button
          id="upload-btn"
          className="upload-primary-btn"
          onClick={handleUpload}
          disabled={isProcessing || !hasFiles}
          aria-label="Upload and process RFP"
        >
          {isProcessing ? (
            <>
              <span className="upload-spinner"></span>
              Processing…
            </>
          ) : (
            'Upload & Process'
          )}
        </button>
      </div>

      {status && (
        <div className={`status ${status.includes('Failed') ? 'error' : ''}`} role="status" aria-live="polite">
          {status}
        </div>
      )}
    </section>
  )
}

