# TestPilot

TestPilot is an AI-assisted web test generation platform with a React frontend and FastAPI backend.

## Hosting

### Backend on Render

1. Create a new **Web Service** on Render.
2. Connect your GitHub repository and choose the `main` branch.
3. Render will detect `render.yaml` in the repo.
4. Add these environment variables in Render:
   - `MONGODB_URI`
   - `MONGODB_DB_NAME` (default: `testpilot`)
   - `GROQ_API_KEY`
   - `PLAYWRIGHT_HEADLESS` (set to `true`)
   - `STORAGE_PATH` (recommended: `../storage`)
5. Render build command is defined in `render.yaml`.

### Frontend on Netlify

1. Create a new site on Netlify and connect your GitHub repo.
2. Use `frontend` as the base directory.
3. Set the build command to `npm install && npm run build`.
4. Set the publish directory to `frontend/dist`.
5. Set an environment variable in Netlify:
   - `VITE_API_BASE_URL=https://<your-render-backend-domain>/api/v1`

## Environment files

- `backend/.env.example` shows backend env settings.
- `frontend/.env.example` shows the frontend API base URL setting.

## Notes

- The backend is served by `backend/app/main.py` and exposes FastAPI routes under `/api/v1`.
- The frontend is a Vite React app that uses `VITE_API_BASE_URL` to connect to the backend.
