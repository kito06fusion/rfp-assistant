import React, { useState, useEffect, useRef } from 'react'
import { usePipeline } from '../context/PipelineContext'
import './LiveFeed.css'

export default function LiveFeed() {
  const { pipelineData, statuses } = usePipeline()
  const [visibleEvents, setVisibleEvents] = useState([])
  const [allEvents, setAllEvents] = useState([])
  const eventsEndRef = useRef(null)

  useEffect(() => {
    const newEvents = []

    // OCR events
    if (pipelineData.ocr) {
      newEvents.push({
        id: 'ocr-complete',
        type: 'success',
        message: 'Text extraction completed',
        order: 1,
      })
    }

    // Preprocess events
    if (pipelineData.preprocess && typeof pipelineData.preprocess === 'object') {
      const pp = pipelineData.preprocess
      let order = 10
      
      if (pp.language && typeof pp.language === 'string') {
        newEvents.push({
          id: 'preprocess-language',
          type: 'info',
          message: 'Language detected',
          order: order++,
        })
      }

      if (pp.key_requirements_summary && typeof pp.key_requirements_summary === 'string') {
        newEvents.push({
          id: 'preprocess-key-req',
          type: 'info',
          message: 'Key requirements found',
          order: order++,
        })
      }

      if (pp.removed_text && typeof pp.removed_text === 'string') {
        newEvents.push({
          id: 'preprocess-removed',
          type: 'warning',
          message: 'Out of scope text removed',
          order: order++,
        })
      }

      if (pp.comparison_agreement !== undefined) {
        newEvents.push({
          id: 'preprocess-comparison',
          type: pp.comparison_agreement ? 'success' : 'warning',
          message: pp.comparison_agreement 
            ? 'Text validation passed'
            : 'Text validation warning - review recommended',
          order: order++,
        })
      }

      newEvents.push({
        id: 'preprocess-complete',
        type: 'success',
        message: 'Preprocessing completed',
        order: order++,
      })
    }

    // Requirements events
    if (pipelineData.requirements && typeof pipelineData.requirements === 'object') {
      const req = pipelineData.requirements
      let order = 100
      
      const solutionReqCount = Array.isArray(req.solution_requirements) ? req.solution_requirements.length : 0
      const responseReqCount = Array.isArray(req.response_structure_requirements) ? req.response_structure_requirements.length : 0
      const totalReqs = solutionReqCount + responseReqCount
      
      if (totalReqs > 0) {
        newEvents.push({
          id: 'req-found',
          type: 'info',
          message: 'Requirements found',
          order: order++,
        })
      }

      // Solution requirements count
      if (solutionReqCount > 0) {
        newEvents.push({
          id: 'req-solution-count',
          type: 'info',
          message: `${solutionReqCount} solution requirement${solutionReqCount !== 1 ? 's' : ''} found`,
          order: order++,
        })
      }

      // Response structure requirements count
      if (responseReqCount > 0) {
        newEvents.push({
          id: 'req-response-count',
          type: 'info',
          message: `${responseReqCount} proposal requirement${responseReqCount !== 1 ? 's' : ''} found`,
          order: order++,
        })
      }

      // Structure detection
      if (req.structure_detection && typeof req.structure_detection === 'object') {
        const sd = req.structure_detection
        if (sd.structure_type !== undefined) {
          newEvents.push({
            id: 'req-structure-detection',
            type: 'info',
            message: `Structure detected: ${sd.structure_type}${sd.confidence ? ` (${(sd.confidence * 100).toFixed(0)}% confidence)` : ''}`,
            order: order++,
          })
        }
      }

      // Final completion message
      if (totalReqs > 0) {
        newEvents.push({
          id: 'req-complete',
          type: 'success',
          message: 'Requirements extraction completed',
          order: order++,
        })
      }
    }

    // Sort by order
    newEvents.sort((a, b) => a.order - b.order)
    setAllEvents(newEvents)
    setVisibleEvents([])
  }, [pipelineData.ocr, pipelineData.preprocess, pipelineData.requirements])

  // Progressive reveal of events
  useEffect(() => {
    if (allEvents.length === 0) return

    let currentIndex = 0
    const interval = setInterval(() => {
      if (currentIndex < allEvents.length) {
        const nextEvent = allEvents[currentIndex]
        if (nextEvent && nextEvent.type && nextEvent.id) {
          setVisibleEvents(prev => [...prev, nextEvent])
        }
        currentIndex++
      } else {
        clearInterval(interval)
      }
    }, 300) // Show one event every 300ms

    return () => clearInterval(interval)
  }, [allEvents])

  // Auto-scroll to bottom when new events appear
  useEffect(() => {
    if (eventsEndRef.current) {
      // Use scrollIntoView with block: 'nearest' to prevent layout shifts
      eventsEndRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  }, [visibleEvents])

  // Determine which phase we're in
  const getCurrentPhase = () => {
    if (statuses.preprocess === 'processing') return 'preprocess'
    if (statuses.requirements === 'processing') return 'requirements'
    if (pipelineData.requirements) return 'requirements'
    if (pipelineData.preprocess) return 'preprocess'
    if (pipelineData.ocr) return 'ocr'
    return 'ocr'
  }

  const currentPhase = getCurrentPhase()

  if (currentPhase === 'ocr' && !pipelineData.ocr) {
    return (
      <div className="live-feed">
        <div className="live-feed-empty">
          <p>Processing feed will appear here during extraction and preprocessing.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="live-feed">
      <div className="live-feed-events">
        {visibleEvents.length === 0 ? (
          <div className="live-feed-empty-state">
            <p>Waiting for processing to begin...</p>
          </div>
        ) : (
          visibleEvents
            .filter(event => event && event.type && event.id)
            .map((event) => (
              <div key={event.id} className={`live-feed-event live-feed-event-${event.type}`}>
                <div className="live-feed-event-icon">
                  {event.type === 'success' && '✓'}
                  {event.type === 'info' && 'ℹ'}
                  {event.type === 'warning' && '⚠'}
                </div>
                <div className="live-feed-event-content">
                  <div className="live-feed-event-message">{event.message || 'Processing...'}</div>
                  {event.detail && (
                    <div className="live-feed-event-detail">{event.detail}</div>
                  )}
                </div>
              </div>
            ))
        )}
        {statuses.preprocess === 'processing' && visibleEvents.length === 0 && (
          <div className="live-feed-event live-feed-event-info">
            <div className="live-feed-event-icon spinning">⟳</div>
            <div className="live-feed-event-content">
              <div className="live-feed-event-message">Processing...</div>
            </div>
          </div>
        )}
        {statuses.requirements === 'processing' && visibleEvents.length === 0 && (
          <div className="live-feed-event live-feed-event-info">
            <div className="live-feed-event-icon spinning">⟳</div>
            <div className="live-feed-event-content">
              <div className="live-feed-event-message">Extracting requirements...</div>
            </div>
          </div>
        )}
        <div ref={eventsEndRef} />
      </div>
    </div>
  )
}

