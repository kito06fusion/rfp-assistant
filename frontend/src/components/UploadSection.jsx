import React, { useState } from 'react'
import { usePipeline } from '../context/PipelineContext'
import { processRFP } from '../services/api'
import './UploadSection.css'

export default function UploadSection() {
  const { updatePipelineData, updateStatus, resetPipeline } = usePipeline()
  const [file, setFile] = useState(null)
  const [status, setStatus] = useState('')
  const [isProcessing, setIsProcessing] = useState(false)

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0]
    setFile(selectedFile)
    setStatus('')
  }

  const handleUpload = async () => {
    if (!file) {
      setStatus('Please choose a PDF or DOCX file first.')
      return
    }

    setIsProcessing(true)
    resetPipeline()
    setStatus('Uploading and running agents… this may take a moment.')

    try {
      updateStatus('extraction', 'processing')
      const data = await processRFP(file)

      // Update pipeline data
      updatePipelineData('ocr', data.ocr_source_text || 'No OCR text returned.')
      updatePipelineData('extraction', data.extraction)
      updatePipelineData('scope', data.scope)

      updateStatus('extraction', 'complete')
      updateStatus('scope', 'complete')
      updateStatus('requirements', 'waiting')

      setStatus('Extraction and scope finished. Review, then accept scope to run requirements.')
    } catch (err) {
      console.error(err)
      setStatus(`Failed to process file: ${err.message}`)
      updateStatus('extraction', 'error')
    } finally {
      setIsProcessing(false)
    }
  }

  return (
    <section className="card">
      <div style={{ marginBottom: '1rem' }}>
        <h2 style={{ margin: 0 }}>RFP Processing</h2>
        <div className="subheading" style={{ marginTop: '0.25rem' }}>
          Upload an RFP document and inspect each agent's view of the text.
        </div>
      </div>
      <div className="upload-row">
        <input
          id="file-input"
          type="file"
          accept=".pdf,.doc,.docx"
          onChange={handleFileChange}
          disabled={isProcessing}
        />
        <button
          id="upload-btn"
          onClick={handleUpload}
          disabled={isProcessing || !file}
        >
          Upload & process
        </button>
      </div>
      {status && (
        <div className={`status ${status.includes('Failed') ? 'error' : ''}`}>
          {status}
        </div>
      )}
    </section>
  )
}

