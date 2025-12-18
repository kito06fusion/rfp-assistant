/**
 * Format preprocess output for display
 * (combines light preprocess metadata + cleaning information)
 */
export function formatPreprocessOutput(preprocess) {
  if (!preprocess) return "No preprocess data available.";
  
  let output = "PREPROCESS RESULTS\n";
  output += "=".repeat(60) + "\n\n";
  
  // Language
  output += "Language: " + (preprocess.language || "Unknown") + "\n\n";
  
  // Key requirements summary (global, not per-requirement)
  if (preprocess.key_requirements_summary) {
    output += "Key Requirements Summary:\n";
    output += "-".repeat(60) + "\n";
    output += preprocess.key_requirements_summary + "\n\n";
  }
  
  // Removed vs cleaned text
  if (preprocess.removed_text && preprocess.removed_text.trim().length > 0) {
    output += "REMOVED TEXT (Out of Scope)\n";
    output += "-".repeat(60) + "\n";
    output += preprocess.removed_text + "\n\n";
  } else {
    output += "REMOVED TEXT: None\n\n";
  }
  
  if (preprocess.cleaned_text && preprocess.cleaned_text.trim().length > 0) {
    output += "CLEANED TEXT (Used for requirements)\n";
    output += "-".repeat(60) + "\n";
    output += preprocess.cleaned_text + "\n\n";
  } else {
    output += "CLEANED TEXT: None\n\n";
  }
  
  // Comparison validation
  if (preprocess.comparison_agreement !== undefined) {
    output += "COMPARISON VALIDATION\n";
    output += "-".repeat(60) + "\n";
    output += "Agreement: " + (preprocess.comparison_agreement ? "Yes" : "No") + "\n";
    if (preprocess.comparison_notes) {
      output += "Notes: " + preprocess.comparison_notes + "\n";
    }
    output += "\n";
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

