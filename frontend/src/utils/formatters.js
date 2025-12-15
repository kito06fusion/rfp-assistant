/**
 * Format extraction output for display
 */
export function formatExtractionOutput(extraction) {
  if (!extraction) return "No extraction data available.";
  
  let output = "EXTRACTION RESULTS\n";
  output += "=".repeat(60) + "\n\n";
  
  output += "Language: " + (extraction.language || "Unknown") + "\n\n";
  
  if (extraction.cpv_codes && extraction.cpv_codes.length > 0) {
    output += "CPV Codes (" + extraction.cpv_codes.length + "):\n";
    extraction.cpv_codes.forEach((code, idx) => {
      output += "   " + (idx + 1) + ". " + code + "\n";
    });
    output += "\n";
  } else {
    output += "CPV Codes: None found\n\n";
  }
  
  if (extraction.other_codes && extraction.other_codes.length > 0) {
    output += "Other Codes (" + extraction.other_codes.length + "):\n";
    extraction.other_codes.forEach((code, idx) => {
      output += "   " + (idx + 1) + ". " + code + "\n";
    });
    output += "\n";
  } else {
    output += "Other Codes: None found\n\n";
  }
  
  if (extraction.key_requirements_summary) {
    output += "Key Requirements Summary:\n";
    output += "-".repeat(60) + "\n";
    output += extraction.key_requirements_summary + "\n\n";
  }
  
  if (extraction.raw_structured && Object.keys(extraction.raw_structured).length > 0) {
    output += "Additional Metadata:\n";
    output += "-".repeat(60) + "\n";
    for (const [key, value] of Object.entries(extraction.raw_structured)) {
      output += key + ": " + JSON.stringify(value) + "\n";
    }
  }
  
  return output;
}

/**
 * Format scope output for display
 */
export function formatScopeOutput(scope) {
  if (!scope) return "No scope data available.";
  
  let output = "SCOPE ANALYSIS\n";
  output += "=".repeat(60) + "\n\n";
  
  if (scope.rationale) {
    output += "Rationale:\n";
    output += "-".repeat(60) + "\n";
    output += scope.rationale + "\n\n";
  }
  
  if (scope.removed_text && scope.removed_text.trim().length > 0) {
    output += "REMOVED TEXT (Out of Scope)\n";
    output += "-".repeat(60) + "\n";
    output += scope.removed_text + "\n\n";
  } else {
    output += "REMOVED TEXT: None\n\n";
  }
  
  if (scope.necessary_text && scope.necessary_text.trim().length > 0) {
    output += "NECESSARY TEXT (Extracted)\n";
    output += "-".repeat(60) + "\n";
    output += scope.necessary_text + "\n\n";
  } else {
    output += "NECESSARY TEXT: None\n\n";
  }
  
  if (scope.comparison_agreement !== undefined) {
    output += "COMPARISON VALIDATION\n";
    output += "-".repeat(60) + "\n";
    output += "Agreement: " + (scope.comparison_agreement ? "Yes" : "No") + "\n";
    if (scope.comparison_notes) {
      output += "Notes: " + scope.comparison_notes + "\n";
    }
    output += "\n";
  }
  
  output += "CLEANED TEXT (Same as Necessary Text)\n";
  output += "-".repeat(60) + "\n";
  if (scope.cleaned_text) {
    output += scope.cleaned_text + "\n\n";
  } else {
    output += "No cleaned text available.\n\n";
  }
  
  return output;
}

/**
 * Format requirements output for display
 */
export function formatRequirementsOutput(requirements) {
  if (!requirements) return "No requirements data available.";
  
  let output = "REQUIREMENTS ANALYSIS\n";
  output += "=".repeat(60) + "\n\n";
  
  if (requirements.solution_requirements && requirements.solution_requirements.length > 0) {
    output += "SOLUTION REQUIREMENTS (" + requirements.solution_requirements.length + ")\n";
    output += "=".repeat(60) + "\n\n";
    requirements.solution_requirements.forEach((req, idx) => {
      output += "[" + (idx + 1) + "]\n";
      output += "-".repeat(60) + "\n";
      output += req.source_text + "\n\n";
    });
  } else {
    output += "SOLUTION REQUIREMENTS: None found\n\n";
  }
  
  if (requirements.response_structure_requirements && requirements.response_structure_requirements.length > 0) {
    output += "RESPONSE STRUCTURE REQUIREMENTS (" + requirements.response_structure_requirements.length + ")\n";
    output += "=".repeat(60) + "\n\n";
    requirements.response_structure_requirements.forEach((req, idx) => {
      output += "[" + (idx + 1) + "]\n";
      output += "-".repeat(60) + "\n";
      output += req.source_text + "\n\n";
    });
  } else {
    output += "RESPONSE STRUCTURE REQUIREMENTS: None found\n\n";
  }
  
  return output;
}

