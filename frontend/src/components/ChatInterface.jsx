import React, { useState, useEffect, useRef } from 'react'
import './ChatInterface.css'
import { enrichBuildQuery, getNextQuestion, submitAnswerAndGetNext } from '../services/api'

const API_BASE = import.meta.env.VITE_API_URL || "http://127.0.0.1:8001"

export default function ChatInterface({ 
  sessionId, 
  onClose, 
  buildQuery, 
  onBuildQueryUpdated,
  requirements,  // For iterative mode
  iterativeMode = false,  // Use iterative one-at-a-time flow
  onAllAnswered,  // Callback when all questions answered
}) {
  const [conversation, setConversation] = useState([]) // Q&A pairs in order
  const [allQuestions, setAllQuestions] = useState([]) // All questions from session
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0)
  const [currentQuestion, setCurrentQuestion] = useState(null) // For iterative mode
  const [remainingGaps, setRemainingGaps] = useState(0)
  const [inputText, setInputText] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isLoadingSession, setIsLoadingSession] = useState(true)
  const [isProcessingAnswer, setIsProcessingAnswer] = useState(false)
  const [allDone, setAllDone] = useState(false)
  const messagesEndRef = useRef(null)

  useEffect(() => {
    if (sessionId) {
      if (iterativeMode && requirements) {
        loadFirstQuestion()
      } else {
        loadSession()
      }
    }
  }, [sessionId, iterativeMode, requirements])

  useEffect(() => {
    scrollToBottom()
  }, [conversation, currentQuestionIndex])

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  // Iterative mode: load first critical question
  const loadFirstQuestion = async () => {
    setIsLoadingSession(true)
    try {
      console.log('Iterative: Getting first critical question')
      const result = await getNextQuestion(requirements, sessionId)
      console.log('First question result:', result)
      
      if (result.question) {
        setCurrentQuestion(result.question)
        setRemainingGaps(result.remaining_gaps || 0)
        setAllQuestions([result.question])
        setAllDone(false)
      } else {
        setCurrentQuestion(null)
        setAllDone(true)
        if (onAllAnswered) onAllAnswered()
      }
    } catch (err) {
      console.error('Failed to get first question:', err)
      setAllDone(true)
      if (onAllAnswered) onAllAnswered()
    } finally {
      setIsLoadingSession(false)
    }
  }

  const loadSession = async () => {
    setIsLoadingSession(true)
    try {
      console.log('Loading chat session:', sessionId)
      const response = await fetch(`${API_BASE}/chat/session/${sessionId}`)
      if (!response.ok) {
        const errorText = await response.text()
        console.error('Failed to load session:', response.status, errorText)
        throw new Error(`Failed to load session: ${response.status}`)
      }
      const data = await response.json()
      console.log('Session data loaded:', data)
      const questions = data.questions || []
      const answers = data.answers || []
      
      console.log(`Loaded ${questions.length} questions, ${answers.length} answers`)
      
      if (questions.length === 0) {
        console.warn('No questions found in session')
      }
      
      setAllQuestions(questions)
      
      // Build conversation history (answered Q&A pairs)
      const history = []
      questions.forEach((q, idx) => {
        const answer = answers.find(a => a.question_id === q.question_id)
        if (answer) {
          history.push({
            question: q,
            answer: answer,
            index: idx,
          })
        }
      })
      setConversation(history)
      
      // Find first unanswered question
      const firstUnanswered = questions.findIndex(q => !q.answered)
      setCurrentQuestionIndex(firstUnanswered >= 0 ? firstUnanswered : questions.length)
      console.log(`Current question index: ${firstUnanswered >= 0 ? firstUnanswered : questions.length}`)
    } catch (err) {
      console.error('Failed to load session:', err)
      // Show error message to user
      alert(`Failed to load questions: ${err.message}. Please refresh the page.`)
    } finally {
      setIsLoadingSession(false)
    }
  }

  // Iterative mode: submit and get next question
  const handleIterativeSubmit = async () => {
    if (!inputText.trim() || isLoading || isProcessingAnswer || !currentQuestion) return

    setIsLoading(true)
    setIsProcessingAnswer(true)
    try {
      const result = await submitAnswerAndGetNext(
        sessionId,
        currentQuestion.question_id,
        currentQuestion.question_text,
        inputText,
        requirements
      )
      console.log('Submit result:', result)
      
      // Add to conversation
      setConversation(prev => [...prev, {
        question: currentQuestion,
        answer: { answer_text: inputText },
        index: prev.length,
      }])
      setInputText('')
      
      if (result.next_question) {
        setCurrentQuestion(result.next_question)
        setRemainingGaps(result.remaining_gaps || 0)
        setAllQuestions(prev => [...prev, result.next_question])
      } else {
        setCurrentQuestion(null)
        setAllDone(true)
        setRemainingGaps(0)
        if (onAllAnswered) onAllAnswered()
      }
      
      // Enrich build query
      if (buildQuery && onBuildQueryUpdated) {
        try {
          const updated = await enrichBuildQuery(buildQuery, sessionId)
          onBuildQueryUpdated(updated)
        } catch (e) {
          console.error('Failed to enrich build query:', e)
        }
      }
    } catch (err) {
      console.error('Failed to submit answer:', err)
      alert('Failed to submit answer. Please try again.')
    } finally {
      setIsLoading(false)
      setIsProcessingAnswer(false)
    }
  }

  const handleSubmitAnswer = async () => {
    // Use iterative mode if enabled
    if (iterativeMode) {
      return handleIterativeSubmit()
    }
    
    if (!inputText.trim() || isLoading || isProcessingAnswer) return

    const currentQ = allQuestions[currentQuestionIndex]
    if (!currentQ) return

    setIsLoading(true)
    setIsProcessingAnswer(true)
    try {
      const response = await fetch(`${API_BASE}/chat/answer`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          session_id: sessionId,
          question_id: currentQ.question_id,
          answer_text: inputText,
        }),
      })

      if (response.ok) {
        const data = await response.json()
        
        // Add to conversation history
        setConversation(prev => [
          ...prev,
          {
            question: currentQ,
            answer: data.answer,
            index: currentQuestionIndex,
          },
        ])
        
        // Move to next question
        const nextIndex = currentQuestionIndex + 1
        setCurrentQuestionIndex(nextIndex)
        setInputText('')
        
        // Reload session to get updated state
        await loadSession()

        // Enrich build query with latest Q&A so the build query view stays in sync
        if (buildQuery && onBuildQueryUpdated) {
          try {
            const updated = await enrichBuildQuery(buildQuery, sessionId)
            onBuildQueryUpdated(updated)
          } catch (e) {
            console.error('Failed to enrich build query:', e)
          }
        }
      } else {
        const errorText = await response.text()
        alert(`Failed to submit answer: ${errorText}`)
      }
    } catch (err) {
      console.error('Failed to submit answer:', err)
      alert('Failed to submit answer. Please try again.')
    } finally {
      setIsLoading(false)
      setIsProcessingAnswer(false)
    }
  }

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      handleSubmitAnswer()
    }
  }

  // In iterative mode, use currentQuestion state; otherwise use array index
  const activeQuestion = iterativeMode ? currentQuestion : allQuestions[currentQuestionIndex]
  const totalQuestions = allQuestions.length
  const answeredCount = conversation.length
  const progress = totalQuestions > 0 ? Math.round((Math.min(answeredCount, totalQuestions) / totalQuestions) * 100) : 0

  if (isLoadingSession) {
    return (
      <div className="chat-interface">
        <div className="chat-header">
          <h3>Interactive Q&A</h3>
          {onClose && (
            <button className="chat-close-btn" onClick={onClose}>×</button>
          )}
        </div>
        <div className="chat-loading">
          <p>Loading questions...</p>
        </div>
      </div>
    )
  }

  // No questions needed (iterative mode found no gaps, or legacy mode has no questions)
  if ((iterativeMode && allDone && answeredCount === 0) || (!iterativeMode && totalQuestions === 0)) {
    return (
      <div className="chat-interface">
        <div className="chat-header">
          <h3>Interactive Q&A</h3>
          {onClose && (
            <button className="chat-close-btn" onClick={onClose}>×</button>
          )}
        </div>
        <div className="chat-empty">
          <p>✓ No questions needed!</p>
          <p style={{fontSize: '0.85rem', color: '#9ca3af', marginTop: '0.5rem'}}>
            All critical information is available in the knowledge base.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="chat-interface">
      <div className="chat-header">
        <div>
          {iterativeMode ? (
            <p className="chat-progress-text">
              {allDone 
                ? `✓ All questions answered (${answeredCount})`
                : `Question ${answeredCount + 1}${remainingGaps > 0 ? ` • ~${remainingGaps} more` : ''}`
              }
            </p>
          ) : (
            <p className="chat-progress-text">
              {answeredCount >= totalQuestions || !activeQuestion
                ? `All ${totalQuestions} questions answered`
                : `Question ${answeredCount + 1} of ${totalQuestions}`
              }
            </p>
          )}
        </div>
        {onClose && (
          <button className="chat-close-btn" onClick={onClose}>×</button>
        )}
      </div>
      
      <div className="chat-messages">
        {/* Show conversation history */}
        {conversation.map((item, idx) => (
          <React.Fragment key={`qa-${idx}`}>
            <div className="chat-message chat-message-question">
              <div className="question-bubble">
                <div className="question-header">
                  <span className="question-label">Question {idx + 1}</span>
                  {item.question.priority && (
                    <span className={`priority-badge priority-${item.question.priority}`}>
                      {item.question.priority}
                    </span>
                  )}
                </div>
                <p className="question-text">{item.question.question_text}</p>
                {item.question.context && (
                  <p className="question-context">Why: {item.question.context}</p>
                )}
              </div>
            </div>
            <div className="chat-message chat-message-answer">
              <div className="answer-bubble">
                <span className="answer-label">Your Answer</span>
                <p className="answer-text">{item.answer.answer_text}</p>
              </div>
            </div>
          </React.Fragment>
        ))}
        
        {/* Show current question */}
        {activeQuestion && !allDone && (
          <div className="current-question-section">
            <div className="chat-message chat-message-question current-question-active">
              <div className="question-bubble question-bubble-current">
                <div className="question-header">
                  <span className="question-label">
                    {iterativeMode 
                      ? `Question ${answeredCount + 1}` 
                      : `Question ${currentQuestionIndex + 1} of ${totalQuestions}`
                    }
                  </span>
                  {activeQuestion.priority && (
                    <span className={`priority-badge priority-${activeQuestion.priority}`}>
                      {activeQuestion.priority}
                    </span>
                  )}
                </div>
                <p className="question-text">{activeQuestion.question_text}</p>
                {activeQuestion.context && (
                  <p className="question-context">Why: {activeQuestion.context}</p>
                )}
              </div>
            </div>
            
            <div className="chat-input-section">
              <div className="input-group">
              <textarea
                className="answer-input"
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onKeyDown={handleKeyPress}
                placeholder="Answer in 3-5 sentences... (Ctrl/Cmd + Enter to submit)"
                rows={4}
                disabled={isLoading || isProcessingAnswer}
                autoFocus
              />
              <button
                className="submit-answer-btn"
                onClick={handleSubmitAnswer}
                disabled={isLoading || isProcessingAnswer || !inputText.trim()}
              >
                {isLoading || isProcessingAnswer ? 'Checking...' : 'Submit →'}
              </button>
              </div>
            </div>
          </div>
        )}
        
        {/* All questions answered */}
        {(allDone || (!activeQuestion && answeredCount > 0)) && (
          <div className="chat-complete">
            <p>✓ All critical questions answered!</p>
            <p className="chat-complete-subtitle">Ready to generate responses.</p>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>
    </div>
  )
}

