const API_BASE =
  import.meta.env.VITE_API_URL || "http://127.0.0.1:8001";

export async function processRFP(files) {
  const formData = new FormData();
  // Support both single file and array of files
  const fileArray = Array.isArray(files) ? files : [files];
  fileArray.forEach((file) => {
    formData.append("files", file);
  });

  const response = await fetch(`${API_BASE}/process-rfp`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Backend error ${response.status}: ${text.slice(0, 200)}`);
  }

  return await response.json();
}

export async function runRequirements(essentialText) {
  const response = await fetch(`${API_BASE}/run-requirements`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      essential_text: essentialText,
    }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Requirements backend error ${response.status}: ${text.slice(0, 200)}`);
  }

  return await response.json();
}

export async function updateRequirements(requirements) {
  const response = await fetch(`${API_BASE}/update-requirements`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ requirements }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Update requirements error ${response.status}: ${text.slice(0, 200)}`);
  }

  return await response.json();
}

export async function buildQuery(preprocess, requirements) {
  const response = await fetch(`${API_BASE}/build-query`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      preprocess,
      requirements,
    }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Build query error ${response.status}: ${text.slice(0, 200)}`);
  }

  return await response.json();
}

export async function generateResponse(preprocess, requirements, options = {}) {
  const { use_rag = true, num_retrieval_chunks = 5, session_id = null } = options;

  const response = await fetch(`${API_BASE}/generate-response`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      preprocess,
      requirements,
      use_rag,
      num_retrieval_chunks,
      session_id, // Include session ID for Q&A context
    }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Response generation error ${response.status}: ${text.slice(0, 200)}`);
  }

  // Handle PDF response
  const contentType = response.headers.get("content-type");
  if (contentType && contentType.includes("application/pdf")) {
    const blob = await response.blob();
    if (blob.size === 0) {
      throw new Error("PDF blob is empty");
    }
    return { type: "pdf", blob };
  }

  // Fallback to JSON if not PDF
  return await response.json();
}

/**
 * Generate questions for build query or requirements
 * When buildQuery is provided, requirements should also be provided for per-requirement analysis
 */
export async function generateQuestions(requirements = null, buildQuery = null) {
  const body = {};
  if (buildQuery) {
    body.build_query = buildQuery;
    if (requirements) {
      body.requirements = requirements;
    }
  } else if (requirements) {
    body.requirements = requirements;
  } else {
    throw new Error("Either requirements or buildQuery must be provided");
  }

  const response = await fetch(`${API_BASE}/generate-questions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Generate questions error ${response.status}: ${text.slice(0, 200)}`);
  }

  return await response.json();
}

export async function createChatSession(requirementId = null) {
  const response = await fetch(`${API_BASE}/chat/session`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ requirement_id: requirementId }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Create session error ${response.status}: ${text.slice(0, 200)}`);
  }

  return await response.json();
}

export async function addQuestionsToSession(sessionId, questions) {
  const response = await fetch(`${API_BASE}/chat/questions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      session_id: sessionId,
      questions,
    }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Add questions error ${response.status}: ${text.slice(0, 200)}`);
  }

  return await response.json();
}

export async function getSession(sessionId) {
  const response = await fetch(`${API_BASE}/chat/session/${sessionId}`);

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Get session error ${response.status}: ${text.slice(0, 200)}`);
  }

  return await response.json();
}

export async function previewResponses(preprocess, requirements, options = {}) {
  const { use_rag = true, num_retrieval_chunks = 5, session_id = null } = options;

  const response = await fetch(`${API_BASE}/preview-responses`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      preprocess,
      requirements,
      use_rag,
      num_retrieval_chunks,
      session_id,
    }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Preview responses error ${response.status}: ${text.slice(0, 200)}`);
  }

  return await response.json();
}

export async function updateResponse(previewId, requirementId, responseText) {
  const response = await fetch(`${API_BASE}/update-response`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      preview_id: previewId,
      requirement_id: requirementId,
      response_text: responseText,
    }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Update response error ${response.status}: ${text.slice(0, 200)}`);
  }

  return await response.json();
}

export async function generatePDFFromPreview(previewId, preprocess, requirements, format = 'pdf') {
  const response = await fetch(`${API_BASE}/generate-pdf-from-preview`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      preview_id: previewId,
      preprocess,
      requirements,
      format,
    }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Generate ${format} error ${response.status}: ${text.slice(0, 200)}`);
  }

  // Handle document response
  const contentType = response.headers.get("content-type");
  const blob = await response.blob();
  if (blob.size === 0) {
    throw new Error(`${format.toUpperCase()} blob is empty`);
  }
  return { type: "blob", blob, format };
}

export async function enrichBuildQuery(buildQuery, sessionId = null) {
  const response = await fetch(`${API_BASE}/enrich-build-query`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      build_query: buildQuery,
      session_id: sessionId,
    }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Enrich build query error ${response.status}: ${text.slice(0, 200)}`);
  }

  return await response.json();
}

// =============================================================================
// ITERATIVE QUESTION FLOW
// =============================================================================

/**
 * Get the next single critical question (iterative flow).
 * Returns null when no more questions needed.
 */
export async function getNextQuestion(requirements, sessionId = null) {
  const response = await fetch(`${API_BASE}/get-next-question`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      requirements,
      session_id: sessionId,
    }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Get next question error ${response.status}: ${text.slice(0, 200)}`);
  }

  return await response.json();
}

/**
 * Submit an answer and get the next question (if any).
 */
export async function submitAnswerAndGetNext(sessionId, questionId, questionText, answerText, requirements) {
  const response = await fetch(`${API_BASE}/submit-answer-get-next`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      question_id: questionId,
      question_text: questionText,
      answer_text: answerText,
      requirements,
    }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Submit answer error ${response.status}: ${text.slice(0, 200)}`);
  }

  return await response.json();
}

