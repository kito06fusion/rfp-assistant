import React, { useState, useEffect, useRef } from 'react'
import './ChatInterface.css'
import { enrichBuildQuery } from '../services/api'

const API_BASE = "http://127.0.0.1:8001"

export default function ChatInterface({ sessionId, onClose, buildQuery, onBuildQueryUpdated }) {
  const [conversation, setConversation] = useState([]) // Q&A pairs in order
  const [allQuestions, setAllQuestions] = useState([]) // All questions from session
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0)
  const [inputText, setInputText] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isLoadingSession, setIsLoadingSession] = useState(true)
  const [isProcessingAnswer, setIsProcessingAnswer] = useState(false)
  const messagesEndRef = useRef(null)

  useEffect(() => {
    if (sessionId) {
      loadSession()
    }
  }, [sessionId])

  useEffect(() => {
    scrollToBottom()
  }, [conversation, currentQuestionIndex])

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
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

  const handleSubmitAnswer = async () => {
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

  const currentQuestion = allQuestions[currentQuestionIndex]
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

  if (totalQuestions === 0) {
    return (
      <div className="chat-interface">
        <div className="chat-header">
          <h3>Interactive Q&A</h3>
          {onClose && (
            <button className="chat-close-btn" onClick={onClose}>×</button>
          )}
        </div>
        <div className="chat-empty">
          <p>No questions available. All information is clear or available in the knowledge base.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="chat-interface">
      <div className="chat-header">
        <div>
          {answeredCount >= totalQuestions || !currentQuestion ? (
            <p className="chat-progress-text">
              All {totalQuestions} questions answered ({progress}% complete)
            </p>
          ) : (
            <p className="chat-progress-text">
              Question {answeredCount + 1} of {totalQuestions} ({progress}% complete)
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
          <React.Fragment key={`qa-${item.index}`}>
            <div className="chat-message chat-message-question">
              <div className="question-bubble">
                <div className="question-header">
                  <span className="question-label">Question {item.index + 1}</span>
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
        
        {/* Show current question prominently */}
        {currentQuestion && (
          <div className="current-question-section">
            <div className="chat-message chat-message-question current-question-active">
              <div className="question-bubble question-bubble-current">
                <div className="question-header">
                  <span className="question-label">Question {currentQuestionIndex + 1} of {totalQuestions}</span>
                  {currentQuestion.priority && (
                    <span className={`priority-badge priority-${currentQuestion.priority}`}>
                      {currentQuestion.priority}
                    </span>
                  )}
                </div>
                <p className="question-text">{currentQuestion.question_text}</p>
                {currentQuestion.context && (
                  <p className="question-context">Why: {currentQuestion.context}</p>
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
                placeholder="Type your answer here... (Ctrl/Cmd + Enter to submit)"
                rows={4}
                disabled={isLoading || isProcessingAnswer}
                autoFocus
              />
              <button
                className="submit-answer-btn"
                onClick={handleSubmitAnswer}
                disabled={isLoading || isProcessingAnswer || !inputText.trim()}
              >
                {isLoading || isProcessingAnswer ? 'Processing...' : 'Submit Answer →'}
              </button>
              </div>
            </div>
          </div>
        )}
        
        {/* All questions answered */}
        {!currentQuestion && totalQuestions > 0 && (
          <div className="chat-complete">
            <p>✓ All {totalQuestions} questions answered!</p>
            <p className="chat-complete-subtitle">You can now proceed to build the query and generate responses.</p>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>
    </div>
  )
}

