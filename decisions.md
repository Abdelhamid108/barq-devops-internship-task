# Technical decisions

Record at least 5 decisions. Include assumptions and limits.

## Decision 1: Application Base Image Selection & Vulnerability Hardening
- Choice: Migrate Flask backend base image from `python:3.12-slim-bookworm` to `python:3.13-alpine@sha256:79e7a9b9ff1cbceff819f856fb374477792a5967759d94df266de7b7b4120e6f`.
- Why:
  1. Massive Vulnerability Reduction: The starter image had 282 total vulnerabilities, including unpatched CRITICAL `zlib1g` (`CVE-2023-45853`). Migrating to Alpine eliminated all 276 OS-level vulnerabilities, bringing the total count down to just 3 (a 99% reduction) and 0 CRITICALs.
  2. Footprint Optimization: Reduced final image size by 50% (222 MB down to 112 MB), drastically improving CI build, transfer, and deployment speeds.
  3. Architecture Harmonization: Standardizes the entire containerized architecture on Alpine Linux, matching `postgres:16-alpine`, `redis:7.4-alpine`, and `nginx:1.28-alpine`.
  4. Verified Compatibility: Empirically verified across all project automation—`validate.py` (21/21 checks passed), `failure_test.py` (100% failover/recovery), `backup.sh` (volume retention), and `restore.sh` (schema restoration).
- Alternative:
  - `python:3.12-slim-bookworm` (Starter): Retains Debian `glibc`, but carries 282 total CVEs including unpatched CRITICAL `zlib1g`.
  - `python:3.13-slim-trixie` (Updated Debian): Eliminates the CRITICAL CVE and keeps standard `groupadd` syntax, but still carries 159 total vulnerabilities (156 in the OS) and remains twice as large (222 MB).
- Trade-off: Alpine uses BusyBox rather than GNU Shadow utils, requiring adapting non-root user creation from `groupadd`/`useradd` to Alpine's `addgroup`/`adduser` syntax. Additionally, packages requiring C compilation would need `musl` build dependencies, though our stack (`psycopg[binary]`, `gunicorn`, `flask`) uses verified pre-compiled `musllinux` wheels.
- Evidence / commit: Commit `a03158d` (`refactor(docker): upgrade app base image to python:3.13-alpine and adapt user creation`).
- Production improvement: Evaluate Google Distroless or Chainguard Wolfi images to eliminate the shell and package manager entirely from production runtime.

### Empirical Image Evaluation Matrix:
| Base Image | OS Base | Total CVEs | CRITICAL | HIGH | OS-Level CVEs | Image Size | Test Suite Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `python:3.12-slim-bookworm` (Starter) | Debian 12 | 282 | 1 (`zlib1g`) | 6 | 276 | 222 MB | Baseline Starter |
| `python:3.13-slim-trixie` (Updated Debian) | Debian 13 | 159 | 0 | 7 | 156 | 222 MB | 21/21 Passed |
| **`python:3.13-alpine` (Chosen)** | **Alpine 3.24** | **3** | **0** | **2** | **0 (Clean!)** | **112 MB** | **All 4 Suites Passed (100%)** |

