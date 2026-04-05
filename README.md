# Spotter Fullstack Assessment

Django + React (Vite) app for **truck trip planning**: geocoded locations, **driving route** on a map (OpenStreetMap tiles + Leaflet), **step-by-step legs** (driving, breaks, pickup/dropoff, fuel), and **ELD-style daily log grids** derived from a simplified **Hours of Service** model.

**Disclaimer:** Output is a **planning aid only**.

## Prerequisites

- **Python 3** with `pip` (virtual environment recommended)
- **Node.js** (LTS) and **npm**

## Environment variables

Create and edit `.env` at the **repository root** as described in **Run locally** (below). See `.env.example` for all keys. Trip routing uses **TomTom Routing API**; set **`TOMTOM_API_KEY`** or planning will fail when the API runs.

Django loads `.env` from the repo root (`ROOT_DIR` in `backend/config/settings.py`). Vite reads `VITE_*` variables from the same root (`envDir` in `frontend/vite.config.js`). Keep `.env` **out of version control** (gitignored).

## Run locally (step by step)

1. **Install prerequisites**  
   Python 3 with `pip`, and Node.js (LTS) with `npm`, available on your `PATH`.

2. **Create `.env` at the repository root** (same folder as this `README`):

   - Windows (PowerShell or CMD, from repo root): `copy .env.example .env`
   - macOS / Linux: `cp .env.example .env`

3. **Edit `.env`** and set **`TOMTOM_API_KEY`** (see `.env.example` and [TomTom Developer Portal](https://developer.tomtom.com/); enable **Routing API** for the key). Trip routing will fail without a valid key when the API is called. Optional: adjust **`SECRET_KEY`**, **`CORS_ALLOWED_ORIGINS`**, etc.

4. **Start the backend** (Terminal 1) — listens on **http://127.0.0.1:8000**:

   ```bash
   cd backend
   python -m venv .venv
   ```

   Activate the virtual environment:

   - Windows (PowerShell): `.\.venv\Scripts\Activate.ps1`
   - Windows (CMD): `.\.venv\Scripts\activate.bat`
   - macOS / Linux: `source .venv/bin/activate`

   Then install dependencies, apply migrations, and run the server:

   ```bash
   pip install -r requirements.txt
   python manage.py migrate
   python manage.py runserver 8000
   ```

5. **Start the frontend** (Terminal 2) — from the **repository root** (parent of `backend/`):

   ```bash
   npm run install:frontend
   npm run dev
   ```

   This starts Vite on **http://localhost:5173**. In development, the dev server **proxies** `/api` to `http://127.0.0.1:8000`, so keep the Django process running.

   Alternative (equivalent): `cd frontend`, then `npm install` and `npm run dev`.

6. **Open the app** in a browser at **http://localhost:5173**.

### Optional root scripts

From the repo root you can also run:

- `npm run build` — production build of the frontend
- `npm run preview` — preview the production build locally
- `npm run lint` — ESLint on the frontend
