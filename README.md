# Spotter Fullstack Assessment

Django + React (Vite) app for **truck trip planning**: geocoded locations, **driving route** on a map (OpenStreetMap tiles + Leaflet), **step-by-step legs** (driving, breaks, pickup/dropoff, fuel), and **ELD-style daily log grids** derived from a simplified **Hours of Service** model.

**Disclaimer:** Output is a **planning aid only**. It is **not** an FMCSA-certified ELD and must not be used as proof of compliance.

## Prerequisites

- **Python 3** with `pip` (virtual environment recommended)
- **Node.js** (LTS) and **npm**

## Configuration

1. At the **repository root**, copy the environment template:

   - Windows: `copy .env.example .env`
   - macOS / Linux: `cp .env.example .env`

2. Edit `.env` and set **`ORS_API_KEY`**. Routing calls OpenRouteService (or a compatible URL via **`ORS_BASE_URL`**). Without a key, trip planning will fail when the API is invoked.

3. Keep `.env` **out of version control** (it should remain gitignored).

Django loads this file from the repo root (`ROOT_DIR` in `backend/config/settings.py`). Vite reads `VITE_*` variables from the same root via `frontend/vite.config.js` (`envDir: '..'`) when needed.

## Run locally

You need **two terminals**: backend (port **8000**) and frontend dev server (port **5173**). In dev, Vite **proxies** `/api` to `http://127.0.0.1:8000`.

### Backend

```bash
cd backend
python -m venv .venv