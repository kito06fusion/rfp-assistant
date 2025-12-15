# RFP Assistant - React Frontend Setup

## Overview
The frontend has been migrated from HTML to React using Vite. This document provides setup and development instructions.

## Prerequisites
- Node.js 18+ and npm/yarn
- Python 3.8+ (for backend)
- Backend server running on `http://127.0.0.1:8001`

## Setup Instructions

### 1. Install Dependencies
```bash
npm install
```

### 2. Start Development Server
```bash
npm run dev
```

The React app will be available at `http://localhost:3000` (or the port Vite assigns).

### 3. Build for Production
```bash
npm run build
```

The built files will be in the `dist/` directory.

### 4. Preview Production Build
```bash
npm run preview
```

## Project Structure

```
frontend/
├── src/
│   ├── components/          # React components
│   │   ├── AgentPanel.jsx   # Main agent display panel
│   │   ├── AgentTabs.jsx    # Tab navigation
│   │   ├── UploadSection.jsx # File upload component
│   │   ├── StatusPill.jsx   # Status indicator
│   │   ├── OutputDisplay.jsx # Formatted output display
│   │   ├── CheckboxControl.jsx # Checkbox with label
│   │   └── Button.jsx       # Reusable button
│   ├── context/             # React Context
│   │   └── PipelineContext.jsx # Pipeline state management
│   ├── services/            # API services
│   │   └── api.js           # Backend API calls
│   ├── utils/               # Utility functions
│   │   └── formatters.js    # Output formatting functions
│   ├── App.jsx              # Main app component
│   ├── main.jsx             # React entry point
│   └── index.css            # Global styles
├── index.html               # HTML template
└── package.json             # Dependencies and scripts
```

## Features

### State Management
- Uses React Context API for global state
- Manages pipeline data (OCR, extraction, scope, requirements, build query, response)
- Tracks processing status for each agent
- Handles user confirmations (scope acceptance, build query confirmation)

### Components
- **UploadSection**: Handles file upload and initial processing
- **AgentTabs**: Tabbed interface for viewing different agent outputs
- **AgentPanel**: Displays agent-specific content with status and controls
- **StatusPill**: Visual status indicator (processing, complete, error)
- **OutputDisplay**: Formatted text output with scrolling
- **CheckboxControl**: Checkbox with label for confirmations
- **Button**: Reusable styled button component

### API Integration
All backend endpoints are integrated:
- `POST /process-rfp` - Upload and process RFP
- `POST /run-requirements` - Run requirements agent
- `POST /build-query` - Build consolidated query
- `POST /generate-response` - Generate PDF response

## Development Notes

### Vite Configuration
- Proxy configured for backend API calls
- Development server on port 3000
- Hot module replacement enabled

### Styling
- CSS modules approach (separate CSS files per component)
- Maintains original dark theme design
- Responsive layout

### PDF Generation Fix
The blank pages issue in PDF generation has been fixed by:
- Changing `page-break-inside: avoid` to `auto` for requirement responses
- Reducing `orphans` and `widows` from 3 to 2
- Allowing content to break across pages when needed

## Troubleshooting

### Backend Connection Issues
- Ensure backend is running on `http://127.0.0.1:8001`
- Check CORS settings in backend if needed
- Verify proxy configuration in `vite.config.js`

### Build Issues
- Clear `node_modules` and reinstall: `rm -rf node_modules && npm install`
- Check Node.js version: `node --version` (should be 18+)

### PDF Download Issues
- Ensure backend PDF generation is working
- Check browser console for errors
- Verify response content-type is `application/pdf`

## Next Steps

See `IMPLEMENTATION_PLAN.md` for remaining phases:
- Phase 2: Response Structure Detection
- Phase 3: Interactive Chatbot
- Phase 4: Enhanced UX
- Phase 5: Testing & Optimization

