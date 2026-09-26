# Security and production-readiness review

Record at least 8 concrete risks or improvements relevant to your final solution.
This is a review requirement, not the number of hidden faults.

For each finding:
- Risk and evidence:
- Impact:
- Implemented fix / commit:
- Production follow-up:
- How to verify:

Cover secrets, ports, container user, image selection, networks, persistence/backup,
logging/monitoring and availability. Separate completed work from planned improvements.

---

## Finding 1: Plaintext Secret Sprawl & Environment Configuration Exposure
- Risk and evidence: In the starter repository, database credentials (`POSTGRES_USER=barq_app`, `POSTGRES_PASSWORD=BarqLabOnly_7qN2vK8c`, `POSTGRES_DB=barq_tasks`) were hardcoded directly in `docker-compose.yml` and committed into git version control. Furthermore, sensitive environment files (`.env`) were not ignored in `.gitignore`, risking accidental leakage of production secrets into public code repositories.
- Impact: Hardcoding credentials allows anyone with read access to the repository to obtain direct administrative credentials to PostgreSQL and Redis. If leaked to version control, credentials can be harvested by automated scanning bots, leading to unauthorized data exfiltration, database tampering, or ransomware extortion.
- Implemented fix / commit:
  1. Decoupled all database credentials from `docker-compose.yml`, replacing hardcoded strings with dynamic Compose environment variable substitution (`${POSTGRES_USER}`, `${POSTGRES_PASSWORD}`, `${POSTGRES_DB}`).
  2. Created a sanitized template [`.env.example`](file:///home/devops/BARQ-Academy/.env.example) containing placeholder keys and non-sensitive defaults.
  3. Appended `.env` and `.env.local` to `.gitignore` (Commit `f8e0259`) to guarantee actual environment secrets are never committed to git.
  4. Configured runtime application secret injection via dedicated environment file (`env_file: ./config/app.env`).
  5. In GitHub Actions CI (`.github/workflows/ci.yml`), configured ephemeral dummy environment variables for automated testing without exposing real production credentials.
- Production follow-up: Integrate an enterprise secret management solution (such as HashiCorp Vault, AWS Secrets Manager, or GCP Secret Manager) with short-lived, dynamically generated database credentials and automated rotation. Authenticate CI/CD runners using OpenID Connect (OIDC) rather than long-lived static tokens.
- How to verify:
  1. Verify `.env` is ignored: `git status --ignored | grep .env` (returns `!! .env`).
  2. Verify no credentials exist in `docker-compose.yml`: `grep -E "BarqLabOnly" docker-compose.yml` (returns 0 matches).
  3. Verify git history contains no secrets: `git log -S "BarqLabOnly_" --oneline` shows credentials are only present in starter legacy commits prior to remediation.

---

## Finding 2: Base Image Vulnerability Surface & Supply Chain CVE Management
- Risk and evidence: The starter container images contained an alarming quantity of known Common Vulnerabilities and Exposures (CVEs) across the entire stack, including multiple CRITICAL and HIGH severity vulnerabilities:
  - App starter (`python:3.12-slim-bookworm`): **282 total CVEs** (5 CRITICAL, 58 HIGH), including an unpatched CRITICAL buffer overflow in `zlib1g` (`CVE-2023-45853`).
  - NGINX starter (`nginx:1.28-alpine`): **200 total CVEs** (2 CRITICAL, 55 HIGH) in `musl`, `libcrypto3`, and NGINX HTTP/2 modules.
  - Redis starter (`redis:7.4-alpine`): **26 total CVEs** (2 HIGH) in `libcrypto3`/`libssl3` (`CVE-2026-45447` OpenSSL PKCS7_verify Use-After-Free).
  - Postgres starter (`postgres:16-alpine@sha256:cf78...`): **74 total CVEs** (1 CRITICAL, 30 HIGH), with 28 vulnerabilities located in the OS base packages.
- Impact: Public-facing containers with known vulnerabilities are susceptible to remote code execution (RCE), cryptographic authentication bypass, denial of service, and memory corruption exploits executed by external attackers.
- Implemented fix / commit:
  1. Migrated all services to hardened, minimal Alpine Linux distributions pinned to cryptographic SHA-256 digests:
     - `python:3.13-alpine@sha256:79e7...` (Commit `a03158d`): Eliminated all 276 OS-level vulnerabilities, reducing total CVEs from 282 down to 3 (0 CRITICALs, 0 OS-level CVEs).
     - `nginx:stable-alpine3.24-slim@sha256:3246...` (Commit `6f4275c`): Eliminated all 200 vulnerabilities down to **0 CVEs (100% clean across all severities)**.
     - `redis:7.4.11-alpine@sha256:858f...` (Commit `1386ef3`): Patched OpenSSL CVEs down to **0 CVEs (100% clean across all severities)**.
     - `postgres:16-alpine@sha256:7218...` (Commit `7deed68`): Eliminated all 28 OS vulnerabilities down to **0 OS-level CVEs**.
  2. Integrated automated Trivy vulnerability scanning into `.github/workflows/ci.yml` (Commit `cf9e925`) using `aquasecurity/trivy-action`, generating SARIF security reports uploaded directly to GitHub Security Code Scanning.
  3. **CI Scanner Triage Policy (`exit-code: 0`):** In CI, the Trivy step scans `barq-app:test` with `exit-code: 0`. We deliberately do not fail the build because the remaining 3 vulnerabilities in `app` are application-layer Python package dependencies (`werkzeug`, `urllib3`) required by the starter Flask code rather than OS-level vulnerabilities. Failing CI on application dependencies requiring upstream application refactoring would completely block continuous deployment; instead, SARIF reports are uploaded for asynchronous security triage while OS-level attack vectors are 100% eliminated.

### Empirical Trivy Vulnerability Reduction Matrix:
| Service | Starter Image | Starter CVEs (Crit/High) | Chosen Hardened Digest | Final CVEs (Crit/High) | OS CVEs | Lang CVEs | Reduction % |
| :--- | :--- | :---: | :--- | :---: | :---: | :---: | :---: |
| **Flask App** | `python:3.12-slim-bookworm` | 282 (5 / 58) | `python:3.13-alpine@sha256:79e7...` | 3 (0 / 2) | **0** | 3 | **98.9%** |
| **NGINX** | `nginx:1.28-alpine` | 200 (2 / 55) | `nginx:stable-alpine3.24-slim@sha256:3246...` | **0 (0 / 0)** | **0** | **0** | **100.0%** |
| **Redis** | `redis:7.4-alpine` | 26 (0 / 2) | `redis:7.4.11-alpine@sha256:858f...` | **0 (0 / 0)** | **0** | **0** | **100.0%** |
| **Postgres** | `postgres:16-alpine (cf78)` | 74 (1 / 30) | `postgres:16-alpine@sha256:7218...` | 46 (1 / 21) | **0** | 46 | **37.8% (0 OS)** |

- Production follow-up: Transition to Google Distroless or Chainguard Wolfi images to eliminate shells (`/bin/sh`) and package managers (`apk`) entirely from production runtime. Implement Dependabot / Renovate to automate patch pull requests for application-layer Python dependencies.
- How to verify: Run `trivy image python:3.13-alpine` (confirms 0 OS-level vulnerabilities) and inspect the GitHub Security tab on the latest CI run.

---

## Finding 3: Root Privilege Escalation & Container Escape Vulnerability (CWE-250)
- Risk and evidence: By default, Docker containers execute processes with `root` privileges (`UID 0`, `GID 0`). The starter `Dockerfile` lacked any user specification, running the Flask API server and Gunicorn workers directly as root inside the container.
- Impact: If an attacker identifies an application-level vulnerability (such as remote code execution via unsafe deserialization or file upload), running as `UID 0` grants the attacker root access within the container namespace. From there, exploiting container runtime flaws or Linux kernel vulnerabilities allows escaping to the host machine with full host root privileges.
- Implemented fix / commit:
  1. In [Dockerfile](file:///home/devops/BARQ-Academy/Dockerfile) (Commit `a03158d`), explicitly created an unprivileged system group and user with fixed IDs: `RUN addgroup -g 10001 -S app && adduser -u 10001 -S -G app -H -D app`.
  2. Assigned ownership of the application directory to the unprivileged user: `COPY --chown=app:app app/ ./app/`.
  3. Enforced unprivileged runtime execution via `USER app` directive before the entrypoint.
- Production follow-up: Enforce read-only root filesystems (`read_only: true`), drop all Linux capabilities (`cap_drop: [ALL]`), and set `securityContext.runAsNonRoot: true` in Kubernetes manifests with strict seccomp (`RuntimeDefault`) and AppArmor profiles.
- How to verify: Execute `docker compose exec app-01 id` (returns `uid=10001(app) gid=10001(app) groups=10001(app)`).

---

## Finding 4: Unauthenticated Public Host Port Exposure & Ingress Bypass
- Risk and evidence: In starter `docker-compose.yml`, PostgreSQL published host port `127.0.0.1:15432:5432` and Redis published host port `127.0.0.1:16379:6379`.
- Impact: Exposing internal database and caching ports to the host network interface allows any local unprivileged process, compromised adjacent container, or network-level attacker to bypass NGINX reverse proxy authentication, rate-limiting, and web application firewall rules. Attackers can execute unauthenticated Redis commands (potentially achieving remote code execution) or directly execute SQL queries against PostgreSQL.
- Implemented fix / commit:
  1. Removed all `ports:` directives from `postgres`, `redis`, and backend `app` containers in `docker-compose.yml` (Commit `fd64c2e`).
  2. Restricted host port binding strictly to NGINX on `127.0.0.1:${PUBLIC_PORT:-8080}:80`.
- Production follow-up: Enforce host-level Linux firewalls (`iptables` / `ufw`), utilize Cloud Security Groups, and run all internal microservices in private subnets with zero public ingress.
- How to verify: Run `python3 validate.py` — passes 4/4 prohibited host port checks (`PASS: container: postgres has no host port`, `redis has no host port`, `app-01 has no host port`, `app-02 has no host port`).

---

## Finding 5: Flat Network Topology & Lateral Movement Vulnerability
- Risk and evidence: In starter `docker-compose.yml`, the NGINX reverse proxy container was joined to both the `frontend` and `backend` networks simultaneously, placing public web traffic on the same broadcast domain as sensitive database storage engines.
- Impact: If an attacker compromises the public-facing NGINX container via an HTTP parser vulnerability or buffer overflow, the dual-homed network configuration allows unrestricted lateral movement: the attacker can establish direct TCP connections to PostgreSQL (`5432`) and Redis (`6379`), completely bypassing application business logic.
- Implemented fix / commit:
  1. Enforced strict dual-tier microsegmentation in `docker-compose.yml` (Commit `68a523a`).
  2. Isolated NGINX strictly to the `frontend` network (`networks: [frontend]`).
  3. Isolated `postgres` and `redis` strictly to the `backend` network (`networks: [backend]`) with `internal: true`.
  4. Assigned backend Flask instances (`app-01`, `app-02`) to bridge both networks (`networks: [frontend, backend]`), acting as the sole authorized application-layer gateways.
- Production follow-up: Implement Kubernetes NetworkPolicies or Cilium eBPF network security rules enforcing zero-trust egress and ingress filtering, paired with mutual TLS (mTLS) service mesh (Istio / Linkerd) to cryptographically verify and encrypt all intra-cluster communications.
- How to verify:
  1. Run `python3 validate.py` — passes 5/5 network isolation checks.
  2. Test direct network connectivity from NGINX to databases: `docker compose exec nginx ping -c 1 -W 2 postgres` (fails with name resolution or network unreachable).

---

## Finding 6: Unencrypted Database Backups Stored on Host Filesystem (CWE-311)
- Risk and evidence: Database backup routines dump raw PostgreSQL schemas and data into plain-text SQL files (`backups/*.sql`) on the local host filesystem via `pg_dump`.
- Impact: Raw SQL dumps store sensitive table records, password hashes, and user data completely unencrypted. Anyone with read access to the backup directory or any compromised process on the host can read, exfiltrate, or tamper with the database contents without authenticating to PostgreSQL. Furthermore, lack of offsite replication risks complete data loss if the host filesystem fails.
- Implemented fix / commit:
  1. Configured persistent named volumes `postgres-data` and `redis-data` (Commit `7deed68` and `1386ef3`) to decouple active data from ephemeral container lifecycles.
  2. Enabled Redis Append-Only File (AOF) persistence (`--appendonly yes`) on persistent volume `redis-data`.
  3. Authored [`backup.sh`](file:///home/devops/BARQ-Academy/backup.sh) and [`restore.sh`](file:///home/devops/BARQ-Academy/restore.sh) with end-to-end automated verification, testing that data survives complete container destruction and re-creation.
  4. Restricted backup directory permissions on creation (`mkdir -p backups && chmod 700 backups`).
- Production follow-up:
  1. Encrypt backups at rest using AES-256 / GPG public key encryption before writing to disk.
  2. Stream encrypted Write-Ahead Logging (WAL) archives and snapshots offsite to immutable cloud object storage (AWS S3 with Object Lock or GCP Cloud Storage with Bucket Lock/Retention Policy).
  3. Implement automated Point-In-Time Recovery (PITR) with tools like `pgBackRest` or `wal-g`.
- How to verify: Run `./backup.sh && ./restore.sh` (confirms record `'backup-proof'` survives container destruction and restores with 100% integrity).

---

## Finding 7: Unsanitized Application Logs & Insufficient Audit Monitoring (CWE-117)
- Risk and evidence: Applications emitting unformatted, unstructured console output are susceptible to Log Injection (CWE-117). Furthermore, standard web frameworks frequently risk accidentally logging database connection strings, passwords, or bearer tokens into log files. The starter stack also lacked centralized audit logging and alerting.
- Impact: An attacker can inject forged CRLF (`\r\n`) characters into HTTP headers or query parameters to fabricate fake log entries, blinding security incident responders or spoofing successful audit events. Additionally, unmasked secrets in logs expose credentials to log aggregation administrators.
- Implemented fix / commit:
  1. Standardized Flask application logging into structured, machine-parseable JSON format (Commit `a03158d`), capturing `timestamp`, `level`, `service`, `event`, `instance_id`, `request_id`, `method`, `path`, `status`, and `duration_ms`.
  2. Separated NGINX access logs (`/dev/stdout`) and error logs (`/dev/stderr`) to provide clean distinction between telemetry streams.
  3. Sanitized configuration logging to ensure raw database passwords are not exposed in application startup logs.
- Production follow-up:
  1. Forward all container logs to a centralized SIEM / log aggregation pipeline (e.g. Grafana Loki, Elasticsearch, or Datadog) with TLS transport encryption.
  2. Implement automated log redaction filters to scrub Authorization headers, credit card numbers, and PII.
  3. Establish real-time alerting on anomalous error rates (e.g. spikes in HTTP 401/403 or 500 errors).
- How to verify: Run `docker compose logs app-01 --tail 10` and pipe to `jq .` (confirms valid, structured JSON output with distinct `request_id` tracking).

---

## Finding 8: Application-Layer Denial of Service (DoS) & Slowloris Vulnerability (CWE-400)
- Risk and evidence: In the starter configuration, NGINX utilized default 60-second timeouts (`proxy_connect_timeout 60s;`, `proxy_read_timeout 60s;`), had no request rate-limiting enabled, and lacked container resource constraints.
- Impact: An attacker can launch Slowloris or slow HTTP POST attacks, opening concurrent TCP connections and transmitting headers very slowly. Because NGINX waited 60 seconds per connection, an attacker with minimal bandwidth could exhaust all available worker connections and Gunicorn worker threads, causing a total Denial of Service (DoS) for legitimate users. Unconstrained memory also risks triggering the host Out-Of-Memory (OOM) killer.
- Implemented fix / commit:
  1. Configured fail-fast upstream timeouts in `nginx/nginx.conf` (Commit `c110ee3`): `proxy_connect_timeout 3s;`, `proxy_read_timeout 4s;`, grounded in empirical log latency percentiles (P95 = 2.001s).
  2. Configured deterministic resource limits across the stack in `docker-compose.yml` (Commit `5f17f48`), capping total stack memory at 1,408 MiB (~35% of a 4 GB VM) to prevent OOM cascades.
  3. Implemented round-robin load balancing across redundant backend replicas (`app-01`, `app-02`), ensuring service continuity when a single replica fails.
- Production follow-up:
  1. Implement NGINX `limit_req_zone` rate-limiting (e.g. `limit_req zone=api burst=20 nodelay;` limiting clients to 10 req/s per IP).
  2. Deploy Web Application Firewall (WAF) rules (e.g. AWS WAF, Cloudflare, or ModSecurity/Coraza) to automatically block volumetric DoS attacks and bot traffic.
  3. Deploy multi-replica NGINX ingress instances across multiple Availability Zones with an external Layer 4/Layer 7 cloud load balancer.
- How to verify: Run `python3 failure_test.py` (proves that when a backend fails, NGINX fails fast and traffic recovers to 100% availability upon backend restoration).
