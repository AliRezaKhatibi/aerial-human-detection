# Aerial Person Studio

A production-oriented desktop starter for aerial person detection and tracking.

**Target architecture**

- Desktop shell: Tauri 2
- Frontend: React + TypeScript + Vite
- UI: Tailwind CSS + shadcn-style local components
- Backend: FastAPI + WebSocket
- Local database: SQLite
- Inference target: YOLO26m-P2 + TensorRT FP16
- Tracking: ByteTrack
- Video: OpenCV + FFmpeg

The repository starts in **mock mode**, so the UI and API can be developed before the trained model is copied into `models/`.

## What is already included

- Commercial dark dashboard shell with Persian RTL and English LTR support
- Pages for dashboard, new analysis, live processing, results, profiles, settings, and system status
- Fast/Balanced/Accuracy inference profiles
- FastAPI health, system, profile, and job endpoints
- Job progress WebSocket
- Mock GPU/video job worker for end-to-end UI development
- Tauri 2 desktop configuration
- Windows PowerShell setup and development scripts
- API contract, design system, and staged roadmap

## Prerequisites on Windows

1. Node.js LTS
2. pnpm
3. Python 3.11 or 3.12
4. Rust stable and Tauri prerequisites
5. NVIDIA driver, CUDA, and TensorRT later for production inference
6. FFmpeg later for production video encoding

## First setup

Open PowerShell in the project root:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
./scripts/setup.ps1
```

## Start development

Terminal 1:

```powershell
./scripts/backend-dev.ps1
```

Terminal 2:

```powershell
./scripts/frontend-dev.ps1
```

Open `http://localhost:1420`.

For the Tauri window, after frontend and backend are confirmed separately:

```powershell
./scripts/tauri-dev.ps1
```

## Backend API

- Swagger: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/api/v1/health`
- Profiles: `http://127.0.0.1:8000/api/v1/profiles`
- Jobs: `http://127.0.0.1:8000/api/v1/jobs`
- WebSocket: `ws://127.0.0.1:8000/api/v1/ws/jobs/{job_id}`

## Model placement

The trained model is deliberately not bundled in the starter. Later place one of these files in `models/`:

```text
models/aerial-person.engine  # preferred production TensorRT engine
models/aerial-person.onnx
models/best.pt               # development fallback
```

Do not build the TensorRT engine on Colab for the final RTX 3070 deployment. Build it on the target machine or a compatible deployment environment.

## Repository map

See `docs/01-architecture.md` and `docs/02-roadmap.md`.
