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
   - `CARGO_HOME` (set to `/tmp/.cargo`)
   - `RUSTUP_HOME` (set to `/tmp/.rustup`)
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

## Deployment checklist

### Render backend checklist

1. Create a new Web Service in Render.
2. Connect the GitHub repository and select branch `main`.
3. Use the existing `render.yaml` in the repo root.
4. Add backend environment variables in Render:
   - `MONGODB_URI`
   - `MONGODB_DB_NAME` (default: `testpilot`)
   - `GROQ_API_KEY`
   - `PLAYWRIGHT_HEADLESS=true`
   - `STORAGE_PATH=../storage`
5. Confirm Render uses the build command and start command from `render.yaml`.
6. Do not commit `backend/.env`; keep secrets in Render env vars.

### Netlify frontend checklist

1. Create a new site in Netlify and connect the same GitHub repo.
2. Set the base directory to `frontend`.
3. Configure the build command:
   - `npm install && npm run build`
4. Configure the publish directory:
   - `frontend/dist`
5. Add the environment variable:
   - `VITE_API_BASE_URL=https://<your-render-backend-domain>/api/v1`
6. Deploy the site and verify the frontend can reach the Render backend.

## Notes

- The backend is served by `backend/app/main.py` and exposes FastAPI routes under `/api/v1`.
- The frontend is a Vite React app that uses `VITE_API_BASE_URL` to connect to the backend.
- The root `.renderignore` and `backend/.renderignore` exclude local build artifacts, secrets, and temporary files from Render deployments.
