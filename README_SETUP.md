# RFP Assistant - Setup Instructions

## Development Setup (Option 2: Single Port)

This setup allows you to access everything through the backend on port 8001.

### Prerequisites
- Python 3.11+
- Node.js 18+
- npm or yarn

### Backend Setup

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Set up environment variables (create `.env` file):
```env
HF_TOKEN=your_huggingface_token
AZURE_OPENAI_API_KEY=your_azure_key
AZURE_OPENAI_ENDPOINT=your_azure_endpoint
AZURE_OPENAI_DEPLOYMENT_NAME=your_deployment_name
```

3. Start the backend:
```bash
uvicorn backend.app:app --host 0.0.0.0 --port 8001 --reload
```

### Frontend Setup

1. Install frontend dependencies:
```bash
npm install
```

2. Build the frontend for production:
```bash
npm run build
```

This creates a `frontend/dist` directory with the built files.

### Access the Application

Once both are set up:
- **Backend**: http://localhost:8001
- **Frontend**: http://localhost:8001 (served by backend)

The backend will automatically serve the frontend from the `frontend/dist` directory after building.

### Development Workflow

For development, you have two options:

**Option A: Rebuild after changes**
1. Make changes to frontend code
2. Run `npm run build`
3. Refresh browser

**Option B: Use Vite dev server (recommended for active development)**
1. Start backend: `uvicorn backend.app:app --host 0.0.0.0 --port 8001 --reload`
2. Start frontend dev server: `npm run dev` (runs on port 3000)
3. Access frontend at: http://localhost:3000
4. Frontend proxies API calls to backend on port 8001

### Production Build

For production deployment:
1. Build frontend: `npm run build`
2. Backend will automatically serve files from `frontend/dist`
3. All routes are handled by the backend on a single port

