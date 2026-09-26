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
| Base Image | OS Base | Total CVEs | CRITICAL | HIGH | MEDIUM | LOW | UNKNOWN | OS CVEs | Lang CVEs | Image Size | Test Suite Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `python:3.12-slim-bookworm` (Starter) | Debian 12 | **282** | 5 | 58 | 112 | 103 | 4 | 276 | 6 | 222 MB | Baseline Starter |
| `python:3.13-slim-trixie` (Updated Debian) | Debian 13 | **159** | **0** | 46 | 54 | 57 | 2 | 156 | 3 | 222 MB | 21/21 Passed |
| **`python:3.13-alpine` (Chosen)** | **Alpine 3.24.2** | **3** | **0** | **2** | 1 | 0 | 0 | **0** | 3 | **112 MB** | **All 4 Suites Passed (100%)** |

---

## Decision 2: NGINX Reverse Proxy Image Selection & Hardening
- Choice: Upgrade NGINX base image from `nginx:1.28-alpine@sha256:a8b39bd9cf0f83869a2162827a0caf6137ddf759d50a171451b335cecc87d236` to `nginx:stable-alpine3.24-slim@sha256:32463212baf0e7d91aded2e9b843a4f2b9e017804b8c9d5bae7b51dcef64389c`.
- Why:
  1. Complete Vulnerability Elimination: The starter image contained 200 total vulnerabilities (including 2 CRITICAL and 55 HIGH CVEs in musl, libcrypto, and NGINX HTTP/2). Migrating to `stable-alpine3.24-slim` eliminated all CVEs, achieving **0 vulnerabilities (100% clean across all severities)**.
  2. Extreme Size Optimization: Reduced container image size by 77% from 93.4 MB down to **21 MB**, significantly shrinking the attack surface.
  3. Reverse Proxy Reliability: Verified with `wget --spider` health checks and routing `/health`, `/ready`, `/records`, and `/instance` to backends with sub-4ms response latencies.
- Alternative:
  - `nginx:1.28-alpine` (Starter): Functional, but leaves 200 unpatched CVEs on the public host port (8080/8090).
  - `nginx:latest` (Debian-based): Large (>140 MB) and introduces Debian OS package vulnerabilities.
- Trade-off: The slim variant removes non-essential NGINX modules and extra utilities, requiring health checks to use lightweight tools (`wget --spider`).
- Evidence / commit: Commit `6f4275c` (`refactor(docker): upgrade nginx to stable-alpine3.24-slim to achieve zero vulnerabilities`).
- Production improvement: Integrate ModSecurity / Coraza Web Application Firewall (WAF) module and automated TLS certificate rotation with Let's Encrypt / Cert-Manager.

### Empirical NGINX Evaluation Matrix:
| Image | Base | Total CVEs | CRITICAL | HIGH | MEDIUM | LOW | UNKNOWN | Image Size | Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `nginx:1.28-alpine` (Starter) | Alpine 3.23.3 | 200 | 2 | 55 | 92 | 49 | 2 | 93.4 MB | Baseline Starter |
| **`nginx:stable-alpine3.24-slim` (Chosen)** | **Alpine 3.24.2** | **0** | **0** | **0** | **0** | **0** | **0** | **21 MB** | **100% Clean, Healthy** |

---

## Decision 3: Redis In-Memory Cache Hardening & Persistence Strategy
- Choice: Upgrade Redis base image to `redis:7.4.11-alpine@sha256:858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499`, configure Append-Only File persistence (`--appendonly yes`), disable RDB snapshots (`--save ""`), and mount `redis-data:/data`.
- Why:
  1. OpenSSL Vulnerability Patching: The starter release `redis:7.4-alpine` contained 26 total vulnerabilities, including 2 HIGH CVEs in `libcrypto3`/`libssl3` (`CVE-2026-45447` OpenSSL PKCS7_verify Use-After-Free). Updating to patch version 7.4.11 on Alpine 3.21.8 eliminated all CVEs, reaching **0 vulnerabilities (100% clean across all severities)**.
  2. Atomic Counter Durability: Enables AOF (`--appendonly yes`) on persistent volume `redis-data` so `/counter` increments survive container restarts without data loss.
  3. Eliminating Fork Latency Spikes: Disabling RDB snapshots (`--save ""`) prevents copy-on-write memory doubling and disk I/O freezes under high load.
  4. Resource Isolation: Limits Redis container to `0.5 CPU` and `256M RAM` to prevent unbounded memory growth from triggering host OOM killer.
- Alternative:
  - `redis:7.4-alpine` (Starter): Contained 26 vulnerabilities including 2 HIGH OpenSSL CVEs.
  - Periodic RDB Snapshotting: Periodically dumps database to disk, but risks losing mutations between snapshot intervals.
  - Ephemeral Redis (No Persistence): Risks losing counter state on container recreation.
- Trade-off: AOF generates continuous sequential write disk I/O and monotonic file growth requiring periodic log compaction (`BGREWRITEAOF`).
- Evidence / commit: Commit `1386ef3` (`refactor(docker): upgrade redis to 7.4.11-alpine to eliminate OpenSSL vulnerabilities`), verified with Trivy scan (0 CVEs) and validated `/counter` increments across container recreation.
- Production improvement: Set `maxmemory 200mb` with LRU eviction policy (`allkeys-lru`) and Redis Sentinel or Redis Cluster replication for high availability.

### Empirical Redis Evaluation Matrix:
| Image | Base | Total CVEs | CRITICAL | HIGH | MEDIUM | LOW | UNKNOWN | Image Size | Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `redis:7.4-alpine` (Starter) | Alpine 3.21.7 | 26 | 0 | 2 | 10 | 14 | 0 | 57.8 MB | Starter baseline |
| **`redis:7.4.11-alpine` (Chosen)** | **Alpine 3.21.8** | **0** | **0** | **0** | **0** | **0** | **0** | **57.8 MB** | **100% Clean, Verified** |

---

## Decision 4: PostgreSQL Image Digest Pinning & Persistent Volume Lifecycle
- Choice: Pin PostgreSQL to `postgres:16-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea` on Alpine 3.24.2, mount named volume `postgres-data:/var/lib/postgresql/data`, attach `./database/init.sql:/docker-entrypoint-initdb.d/01-init.sql:ro`, and configure native `pg_isready` healthcheck.
- Why:
  1. Complete OS-Level CVE Elimination: Upgrading from the starter digest (`sha256:cf78...`) eliminated all 28 OS-level vulnerabilities, reducing total CVEs from 74 down to 46 (a 38% reduction) with **0 OS-level vulnerabilities**.
  2. Volume Persistence Guarantee: Named volume `postgres-data` decouples database state from the container lifecycle. Empirically proven via `./backup.sh` where data survived complete container destruction and recreation (`docker compose rm -f postgres && docker compose up -d`).
  3. Schema Determinism: The read-only (`:ro`) mount of `01-init.sql` prevents container runtime processes from tampering with the baseline DDL schema while guaranteeing automated table creation on first initialization.
  4. Health-Dependent Initialization: Flask backend replicas (`app-01`, `app-02`) declare `depends_on: postgres: condition: service_healthy` using `pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}`, preventing connection refusals during startup.
- Alternative:
  - Ephemeral Container Storage (No Volume): Database records are destroyed whenever the container is updated, restarted, or recreated.
  - Host Bind Mount (`./data:/var/lib/postgresql/data`): Introduces host file permission issues (UID 70 postgres inside container) and host OS filesystem lock discrepancies.
  - Floating Tag (`postgres:16-alpine` unpinned): Risks non-deterministic CI builds and unexpected breaking changes during automated deployments.
- Trade-off: Named volumes persist on the host independently of `docker compose down`, requiring automated disaster recovery routines (`backup.sh` and `restore.sh`) for data migration and cleanup.
- Evidence / commit: Commit `7deed68` (`refactor(docker): update postgres:16-alpine to verified secure digest`), verified with `backup.sh` (volume retention test passed) and `restore.sh` (100% data restored).
- Production improvement: Implement Write-Ahead Logging (WAL) archiving with `pgBackRest` or `wal-g` pushing to object storage (GCS/S3) and provision streaming replication read-replicas.

### Empirical PostgreSQL Evaluation Matrix:
| Image Digest | Base OS | Total CVEs | CRITICAL | HIGH | MEDIUM | LOW | UNKNOWN | OS CVEs | Lang CVEs | Image Size | Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `postgres:16-alpine@sha256:cf78...` (Starter) | Alpine 3.21 | 74 | 1 | 30 | 28 | 14 | 1 | 28 | 46 | 420 MB | Starter Baseline |
| **`postgres:16-alpine@sha256:7218...` (Chosen)** | **Alpine 3.24.2** | **46** | 1 | **21** | **21** | **2** | 1 | **0 (Clean!)** | 46 | **420 MB** | **0 OS CVEs, Verified** |

---

## Decision 5: Single-Job CI Pipeline Architecture vs. Multi-Job Model
- Choice: Implement a single unified job (`build-scan-validate`) in GitHub Actions rather than the standard multi-job pipeline pattern.
- Why:
  1. Standard vs. Task Scope: In enterprise CI/CD, the standard pattern is separating stages into independent jobs (`build` -> `scan` -> `test`). However, separate GitHub Actions jobs run on isolated ephemeral VMs that do not share the Docker daemon.
  2. Avoidance of Tarball Overhead: Without an external container registry to push and pull images, passing built images across separate jobs requires archiving them as tarballs (`docker save`), uploading them via `actions/upload-artifact`, downloading them, and reloading them (`docker load`). This introduces heavy disk I/O serialization and runner latency with zero functional gain.
  3. Self-Contained Repository Constraint: Pushing to a registry requires external service dependencies and credentials (PAT / secrets), which falls outside the self-contained scope of this project.
  4. Docker Daemon Locality: Keeping all steps in a single job preserves local layer caching: the image built in step 4 is immediately scanned by Trivy in step 5 and launched by `docker compose` in step 8 to run `validate.py`, executing the entire pipeline in **57 seconds**.
- Alternative:
  - Multi-Job Pipeline with External Registry (Industry Standard): Separate jobs where `build` pushes tagged images to GHCR/Docker Hub and subsequent jobs pull them.
    *Limitation:* Requires external registry infrastructure and credentials.
  - Multi-Job Pipeline with Image Tarballs: Passing images between jobs using `docker save` and workflow artifacts.
    *Limitation:* Substantial I/O serialization and transfer overhead.
- Trade-off: Departs from strict multi-job separation of concerns, but eliminates unnecessary image serialization overhead and keeps the pipeline hermetic and fast.
- Evidence / commit: Commit `cf9e925` (`ci: implement automated build-scan-validate pipeline with trivy sarif scanning`), verified live in GitHub Actions run (57s total execution, 21/21 checks passed, Trivy SARIF uploaded).
- Production improvement: In an enterprise environment, transition to the standard multi-job architecture with a secure private registry (e.g., AWS ECR or Google Artifact Registry) and OIDC-based authentication.

---

## Decision 6: Container Health Checks & Service Dependency Ordering
- Choice: Complete the container health check configuration across the stack by adding the missing health check for the NGINX reverse proxy using `wget --spider -q http://127.0.0.1:80/health || exit 1`.
- Task Requirement: The task requires all containers in the multi-container stack to define working health checks and report a `healthy` status during validation (`validate.py`), and backend applications must not start until backing database services are fully healthy.
- Existing vs. Added Implementation:
  - Already implemented in starter stack:
    1. `postgres`: Health check using native `pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}`.
    2. `redis`: Health check using native `redis-cli ping`.
    3. `app` (`app-01`, `app-02`): Health check using Python's standard library `urllib.request` probing `http://127.0.0.1:8080/health`.
  - Added by candidate: `nginx` had no health check defined in the starter `docker-compose.yml`. We added an NGINX health check using BusyBox `wget --spider` probing `/health` locally with `interval: 5s`, `timeout: 3s`, `retries: 3`, and `start_period: 3s`.
- Why `wget --spider`: The hardened `nginx:stable-alpine3.24-slim` base image does not include `curl`. It includes BusyBox `wget`. `--spider` verifies HTTP 200 response headers without downloading response content, and `-q` prevents log noise.
- Alternative: Install `curl` inside the NGINX image (`apk add curl`).
  *Limitation:* Unnecessarily increases container image size and expands attack surface when `wget` is already present.
- Evidence / commit: Commit `b957f9b` (`feat(compose): add NGINX healthcheck and enforce service_healthy startup order`), verified via `validate.py` (5/5 container health checks passed).
- Production improvement: Expose dedicated Prometheus health metrics via `/stub_status` or an OpenTelemetry exporter to alert on upstream connection degradation before container restarts occur.
