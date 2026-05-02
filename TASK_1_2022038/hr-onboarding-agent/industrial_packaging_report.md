# Industrial Packaging and Deployment Strategy

## 1) Reproducible container image

- **Base image choice:** `python:3.11-slim` pinned by digest in `Dockerfile`.  
  This keeps the image small while locking the exact root filesystem for deterministic builds.
- **Layer ordering strategy:** `requirements.txt` is copied and installed before app code so dependency layers are cached across source-only edits.
- **Multi-stage decision:** a single-stage build is used intentionally because there is no compile step (pure Python runtime).  
  A multi-stage build would add complexity without reducing runtime artifacts in this project.

## 2) Secret-free image and runtime injection

- No `.env` or key material is copied into the image (`.dockerignore` excludes `.env` and local runtime files).
- Secrets are injected **only at runtime** in `docker-compose.yaml`:
  - `OPENAI_API_KEY: "${OPENAI_API_KEY:-}"`
  - `LANGSMITH_API_KEY: "${LANGSMITH_API_KEY:-}"`
- CI secrets are injected from GitHub Secrets in `.github/workflows/main.yml`.

Example runtime start:

```bash
OPENAI_API_KEY=... LANGSMITH_API_KEY=... docker compose up -d --build
```

## 3) Multi-service orchestration and persistence

- `docker-compose.yaml` starts two services:
  - `agent` (FastAPI API on `:8000`)
  - `chroma` (vector datastore on `:8001`)
- **Service discovery:** `agent` reaches datastore via Compose DNS name `http://chroma:8000` (`VECTOR_DB_URL`).
- **Startup ordering:** `agent` waits for `chroma` healthcheck to pass.
- **Persistence:**
  - `checkpoint_data` volume stores `checkpoint_db.sqlite`
  - `vector_data` volume stores Chroma data under `/chroma/chroma`
- Both services stop together with:

```bash
docker compose down
```

## 4) End-to-end packaged evidence

- Build/runtime evidence is in `docker_build.log`:
  - `docker compose build`
  - `docker compose up -d`
  - `docker ps` showing both containers running
- API evidence is in `api_test_results.txt` (successful `/chat` and `/stream` calls with valid responses).

## 5) Automated Quality Gate (CI/CD)

- `run_eval.py` is CI-ready and headless:
  - reads paths and credentials from environment variables
  - writes machine-readable JSON (`output/eval_results.json`)
  - exits `0` when all thresholds pass, `1` otherwise
- `eval_thresholds.json` (and `eval_threshold_config.json`) version thresholds with at least 2 metrics.
- `.github/workflows/main.yml` runs on every push to `main`, installs dependencies, runs `run_eval.py`, and uploads eval results artifact.

## 6) Threshold rationale

- **Faithfulness = 0.70**  
  Lower than this means answers are frequently missing expected grounded elements; reliability drops for production support.
- **Relevancy = 0.25**  
  This metric is lexical-overlap-based in this evaluator, so the threshold is calibrated to avoid over-penalizing valid paraphrases while still catching major drift.
- If thresholds were **10% higher**, false failures increase and block healthy changes.  
  If **10% lower**, degraded responses may pass and reduce gate value.

## 7) Breaking-change demonstration procedure

Local proof in this repository:

- **Passing state:** `run_eval.py` with `eval_thresholds.json` writes `output/eval_results.json` and exits `0`.
- **Failing state (demonstration):** `run_eval.py` with `eval_thresholds_strict_demo.json` writes `output/eval_results_fail_demo.json` and exits `1`.

CI proof workflow:

1. Introduce a known degradation (for example, alter safe-refusal logic or remove retrieval branch).
2. Push to a test branch merged into `main`.
3. Observe workflow failure (red) due to threshold breach.
4. Revert degradation and push again.
5. Observe workflow pass (green) with thresholds satisfied.

Store screenshots of both runs in your final submission package for explicit proof.
