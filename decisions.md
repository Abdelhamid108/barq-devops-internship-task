# Technical decisions

Record at least 5 decisions. Include assumptions and limits.

## Decision 1: Stack-Wide Base Image Strategy & Architectural Harmonization
- Choice: Standardize all container services across the multi-container stack on minimal, Alpine-based distributions with pinned immutable SHA-256 digests:
  - Backend API: `python:3.13-alpine@sha256:79e7a9b9ff1cbceff819f856fb374477792a5967759d94df266de7b7b4120e6f`
  - Reverse Proxy: `nginx:stable-alpine3.24-slim@sha256:32463212baf0e7d91aded2e9b843a4f2b9e017804b8c9d5bae7b51dcef64389c`
  - In-Memory Cache: `redis:7.4.11-alpine@sha256:858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499`
  - Relational Database: `postgres:16-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea`
- Why:
  1. *Architectural Harmonization:* Standardizes all 4 services on a single operating system lineage (Alpine Linux 3.21/3.24) with `musl libc` and BusyBox utilities. This eliminates cross-distribution discrepancies, simplifies operational debugging (e.g. uniform shell and network diagnostics), and establishes a consistent runtime paradigm.
  2. *Extreme Footprint Optimization:* Reduces total container image sizes by 50%–77% (App: 222 MB down to 112 MB; NGINX: 93.4 MB down to 21 MB; Redis: 57.8 MB; Postgres: 420 MB). Slashed transfer sizes significantly accelerate CI build pipelines, pull speeds, and cold container startup on resource-constrained hosts.
  3. *Digest Pinning for Determinism & Immutability:* Using cryptographic SHA-256 digests (`@sha256:...`) instead of floating tags (`:latest` or `:16-alpine`) prevents unexpected upstream layer drift, guaranteeing byte-for-byte reproducible builds across developer workstations, GitHub Actions runners, and evaluation environments.
  4. *Verified Library Compatibility:* Validated that Python C extensions (`psycopg[binary]`) install pre-compiled `musllinux` wheels cleanly without requiring heavy build toolchains (`gcc`, `musl-dev`) inside production runtime images.
  *(Note: Detailed vulnerability CVE counts, security exploit scenarios, and CI scanner triage policies are documented in `security_review.md`).*
- Alternative:
  - *Debian-based images (`*-slim-bookworm` / `*-slim-trixie`):* Retains GNU `glibc` and standard shadow utils (`groupadd`), but results in 2x larger images and cross-distribution fragmentation across services.
  - *Floating Image Tags:* Simple to configure, but introduces non-deterministic deployments and risks unexpected breaking changes during automated CI builds.
- Trade-off: Alpine uses BusyBox rather than GNU Shadow utils, requiring adapting non-root user creation from `groupadd`/`useradd` to Alpine's `addgroup`/`adduser` syntax. Additionally, packages requiring compilation from source would need `musl` build dependencies, though our stack uses verified pre-compiled wheels.
- Evidence / commit: Commits `a03158d`, `6f4275c`, `1386ef3`, `7deed68`.
- Production improvement: Evaluate Google Distroless or Chainguard Wolfi images to eliminate the shell and package manager entirely from production runtime.

---

## Decision 2: Redis In-Memory Cache Persistence Strategy
- Choice: Configure Redis Append-Only File (AOF) persistence (`--appendonly yes`), disable periodic RDB point-in-time snapshots (`--save ""`), and mount persistent named volume `redis-data:/data`.
- Why:
  1. *Atomic Mutation Durability:* AOF writes every write operation received by the server to disk sequentially, guaranteeing that atomic counter increments (`/counter`) survive container restarts and sudden process crashes without data loss.
  2. *Eliminating Fork Latency & Memory Spikes:* Disabling RDB snapshots (`--save ""`) prevents Redis from calling `fork()` to dump memory pages to disk, which would double memory consumption (copy-on-write) and cause latency spikes under container memory limits (`mem_limit: 256M`).
- Alternative:
  - *Periodic RDB Snapshotting (Default):* Dumps database state at scheduled intervals (e.g. every 60s), but risks losing all counter mutations executed between snapshot intervals.
  - *Ephemeral Redis (No Persistence):* In-memory only; destroys all cache and counter state whenever the container is recreated or upgraded.
- Trade-off: AOF generates continuous sequential write disk I/O and monotonic log file growth, requiring background log compaction (`BGREWRITEAOF`) to reclaim storage.
- Evidence / commit: Commit `1386ef3`, verified by incrementing `/counter` and verifying retention after container recreation.
- Production improvement: Configure `maxmemory 200mb` with an eviction policy (`allkeys-lru`) and provision Redis Sentinel or Redis Cluster for automatic failover.

---

## Decision 3: PostgreSQL Persistent Volume Lifecycle & Schema Determinism
- Choice: Mount persistent named volume `postgres-data:/var/lib/postgresql/data`, attach `./database/init.sql:/docker-entrypoint-initdb.d/01-init.sql:ro`, and configure native `pg_isready` healthcheck.
- Why:
  1. *Volume Persistence Guarantee:* Named volume `postgres-data` decouples database state from the container lifecycle. Empirically proven via `./backup.sh` where database records survived complete container destruction and recreation (`docker compose rm -f postgres && docker compose up -d`).
  2. *Schema Determinism:* The read-only (`:ro`) mount of `01-init.sql` prevents container runtime processes from tampering with the baseline DDL schema while guaranteeing automated table creation on first initialization.
  3. *Health-Dependent Initialization:* Flask backend replicas declare `depends_on: postgres: condition: service_healthy` using `pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}`, preventing connection refusals during startup.
- Alternative:
  - *Ephemeral Container Storage (No Volume):* Database records are destroyed whenever the container is updated, restarted, or recreated.
  - *Host Bind Mount (`./data:/var/lib/postgresql/data`):* Introduces host file permission issues (UID 70 postgres inside container) and host OS filesystem lock discrepancies.
- Trade-off: Named volumes persist on the host independently of `docker compose down`, requiring automated disaster recovery routines (`backup.sh` and `restore.sh`) for data migration and cleanup.
- Evidence / commit: Commit `7deed68`, verified with `backup.sh` (volume retention test passed) and `restore.sh` (100% data restored).
- Production improvement: Implement Write-Ahead Logging (WAL) archiving with `pgBackRest` or `wal-g` pushing to object storage (GCS/S3) and provision streaming replication read-replicas.

---

## Decision 4: Single-Job CI Pipeline Architecture vs. Multi-Job Model
- Choice: Implement a single unified job (`build-scan-validate`) in GitHub Actions rather than the standard multi-job pipeline pattern.
- Why:
  1. *Standard vs. Task Scope:* In enterprise CI/CD, the standard pattern is separating stages into independent jobs (`build` -> `scan` -> `test`). However, separate GitHub Actions jobs run on isolated ephemeral VMs that do not share the Docker daemon.
  2. *Avoidance of Tarball Overhead:* Without an external container registry to push and pull images, passing built images across separate jobs requires archiving them as tarballs (`docker save`), uploading them via `actions/upload-artifact`, downloading them, and reloading them (`docker load`). This introduces heavy disk I/O serialization and runner latency with zero functional gain.
  3. *Self-Contained Repository Constraint:* Pushing to a registry requires external service dependencies and credentials (PAT / secrets), which falls outside the self-contained scope of this project.
  4. *Docker Daemon Locality:* Keeping all steps in a single job preserves local layer caching: the image built in step 4 is immediately scanned by Trivy in step 5 and launched by `docker compose` in step 8 to run `validate.py`, executing the entire pipeline in **57 seconds**.
- Alternative:
  - *Multi-Job Pipeline with External Registry (Industry Standard):* Separate jobs where `build` pushes tagged images to GHCR/Docker Hub and subsequent jobs pull them.
    *Limitation:* Requires external registry infrastructure and credentials.
  - *Multi-Job Pipeline with Image Tarballs:* Passing images between jobs using `docker save` and workflow artifacts.
    *Limitation:* Substantial I/O serialization and transfer overhead.
- Trade-off: Departs from strict multi-job separation of concerns, but eliminates unnecessary image serialization overhead and keeps the pipeline hermetic and fast.
- Evidence / commit: Commit `cf9e925`, verified live in GitHub Actions run (57s total execution, 21/21 checks passed, Trivy SARIF uploaded).
- Production improvement: In an enterprise environment, transition to the standard multi-job architecture with a secure private registry (e.g., AWS ECR or Google Artifact Registry) and OIDC-based authentication.

---

## Decision 5: Container Health Checks & Service Dependency Ordering
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
- Evidence / commit: Commit `b957f9b`, verified via `validate.py` (5/5 container health checks passed).
- Production improvement: Expose dedicated Prometheus health metrics via `/stub_status` or an OpenTelemetry exporter to alert on upstream connection degradation before container restarts occur.

---

## Decision 6: NGINX Upstream Timeouts & Retries Grounded in Log Analysis
- Choice: Set `proxy_connect_timeout 3s;`, `proxy_read_timeout 4s;`, and `proxy_next_upstream off;` in `nginx/nginx.conf`.
- Why:
  1. *Based on Log Latency Data:* Historical access logs showed a median latency of 54 ms and a 95th percentile (P95) latency of 2.001 s.
  2. *Fail-Fast with Safety Buffer:* Setting connect timeout to 3s provides a 1-second safety buffer above P95 (2.001s) to prevent dropping slow requests, while failing fast within 3s instead of NGINX's default 60s freeze when a backend crashes.
  3. *Database Read Headroom:* Setting read timeout to 4s gives sufficient time for PostgreSQL `/records` queries.
  4. *Task Requirement for Error Measurement:* Keeping `proxy_next_upstream off` allows `./failure_test.py` to measure real errors during backend outage (e.g., 30%–40% availability), as required by the task and video demonstration.
- Alternative:
  - *Default NGINX Timeouts (60s):* Leaves users waiting for 60 seconds during container failure.
  - *Aggressive 2s Timeout:* Too close to the 2.001s P95 threshold, risking false-positive errors during small load spikes.
- Trade-off: Stopped backends return 502 Bad Gateway immediately instead of being silently retried.
- Evidence / commit: Commit `c110ee3`, verified with `failure_test.py` and `validate.py`.
- Production improvement: In enterprise production, enable `proxy_next_upstream error timeout http_502 http_503;` to automatically retry surviving backends without user-facing errors.

---

## Decision 7: Dual-Tier Network Segmentation & Host Port Isolation
- Choice: Partition the multi-container stack into two isolated Docker bridge networks (`frontend` and `backend`), isolate NGINX to `frontend`, isolate databases to `backend`, and unpublish all internal container host ports.
- Task Requirement: The task mandates:
  1. Connect NGINX + apps to `frontend`, and apps + PostgreSQL + Redis to `backend`.
  2. Block direct NGINX access to PostgreSQL and Redis.
  3. Publish only NGINX on host port 8080 (or 8090). Do not publish app, PostgreSQL, or Redis ports to the host.
- Starter State vs. Implemented Fixes:
  - Starter repository violations:
    1. NGINX was connected to both `[frontend, backend]`, exposing PostgreSQL and Redis directly to the public reverse proxy.
    2. PostgreSQL published host port `127.0.0.1:15432:5432`.
    3. Redis published host port `127.0.0.1:16379:6379`.
  - Implemented fixes:
    1. Removed `backend` network from NGINX, strictly isolating it to `frontend` (Commit `68a523a`).
    2. Removed prohibited host ports from PostgreSQL and Redis (Commit `fd64c2e`).
    3. Kept Flask app replicas on both networks (`[frontend, backend]`) to act as the only authorized application-layer bridge.
- Why: Implements zero-trust network microsegmentation. If the public-facing NGINX container is compromised, the attacker cannot reach database ports (5432, 6379) or query data directly.
- Alternative:
  - *Flat Single Bridge Network:* All containers share one network, allowing lateral movement from NGINX to databases.
  - *Host Port Exposure:* Exposing internal ports allows unauthorized local processes to bypass NGINX and query databases directly.
- Trade-off: Developers cannot connect host GUI database clients (such as DBeaver or TablePlus) directly to localhost. Ad-hoc queries and backups must be executed via `docker compose exec` into the containers.
- Evidence / commit: Commits `68a523a` and `fd64c2e`, verified via `validate.py` passing 5/5 network isolation checks and 4/4 prohibited host port checks.
- Production improvement: Enforce Kubernetes NetworkPolicies or service mesh mTLS (e.g. Istio / Cilium) to cryptographically verify container identities and encrypt intra-cluster traffic in transit.

---

## Decision 8: Container Resource Allocation
- Choice: Define explicit, deterministic CPU and memory resource limits for every service in `docker-compose.yml`:
  - `postgres`: `cpus: "0.5"`, `mem_limit: "512M"`
  - `redis`: `cpus: "0.5"`, `mem_limit: "256M"`
  - `app-01`: `cpus: "0.5"`, `mem_limit: "256M"`
  - `app-02`: `cpus: "0.5"`, `mem_limit: "256M"`
  - `nginx`: `cpus: "0.25"`, `mem_limit: "128M"`
  - **Stack Total Upper Bound:** **2.25 vCPUs** and **1,408 MiB RAM** (~1.375 GiB).
- Task Requirement: Line 29 of `TASK.md` requires setting resource limits across the stack, sized to run predictably within the evaluation VM capacity (4 vCPUs, 4 GB RAM).
- Why:
  1. *Host Protection & OOM Prevention:* Uncapped containers risk consuming 100% of host CPU and memory. Capping aggregate container memory at 1,408 MiB ensures the stack consumes at most 35% of a 4 GB host, leaving 2.6 GiB of headroom for Linux kernel page cache, Docker daemon, CI build runners, and automated testing scripts.
  2. *Grounded in Empirical Consumption Telemetry:* Live `docker stats` telemetry proves the active stack consumes only **~103.6 MiB** total RAM (~7.4% of allocated limits). The assigned limits provide 3x–7x headroom for database buffer pools, Redis AOF compaction buffers, and Python GC allocation bursts without triggering the kernel Out-Of-Memory (OOM) killer.
  3. *CPU Quota vs. Boot Latency Balance:* Allocating 0.5 CPU to Flask replicas ensures Python interpreter initialization and module imports (`psycopg`, `flask`) complete in 14–16 seconds on cold container boot without starving the host OS or other containers.
- Alternative:
  - *Unbounded Limits (Docker Default):* Containers can consume unlimited host resources. A single runaway query or memory leak risks freezing the VM and killing critical system services (such as `dockerd` or `sshd`).
  - *Aggressively Constrained Limits (`cpus: "0.1"`, `mem_limit: "64M"`):* Python's baseline runtime footprint (36 MB) leaves negligible headroom, triggering OOM container termination (exit code 137) during request bursts, while CPU CFS throttling stretches startup beyond 35 seconds.
- Trade-off: Hard CPU limits enforced via Linux CFS quota prevent burst processing beyond the allotted share, capping single-container throughput under unexpected traffic spikes.
- Evidence / commit: Empirically verified via `docker stats --no-stream` and `scratch/benchmark_resources.py`, with all 5 services running stable, passing 21/21 checks in `validate.py`, and recovering cleanly in `failure_test.py`.
- Production improvement: In Kubernetes production, separate `requests` (guaranteed resource reservation for node scheduling) from `limits` (hard enforcement ceilings), and configure Horizontal Pod Autoscaling (HPA) targeting 70% CPU/memory utilization.

### Empirical Stack Resource Telemetry Matrix:
| Container | CPU Limit | Actual CPU (Idle) | Actual CPU (Under Load) | Memory Limit | Actual Memory (Active) | Memory Utilization % | Active PIDs |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `postgres` | 0.50 | 0.03% | 0.05% | 512 MiB | 24.18 MiB | 4.72% | 6 |
| `redis` | 0.50 | 0.47% | 2.10% | 256 MiB | 3.25 MiB | 1.27% | 6 |
| `app-01` | 0.50 | 0.39% | 1.20% | 256 MiB | 35.59 MiB | 13.90% | 2 |
| `app-02` | 0.50 | 0.04% | 1.15% | 256 MiB | 35.59 MiB | 13.90% | 2 |
| `nginx` | 0.25 | 0.00% | 14.90% | 128 MiB | 5.00 MiB | 3.90% | 5 |
| **Total Stack** | **2.25 vCPUs** | **~0.93%** | **~19.40%** | **1,408 MiB (1.375 GiB)** | **~103.61 MiB** | **~7.36%** | **21** |
