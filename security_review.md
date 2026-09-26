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
- Impact: Hardcoding credentials allows anyone with read access to the repository to obtain administrative credentials to PostgreSQL and Redis. If pushed to public version control, credentials can be harvested by automated scanning bots, leading to unauthorized data exfiltration, database tampering, or ransomware extortion.
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

## Finding 2: Flask Application Base Image Vulnerabilities & CI Scanner Triage Policy
- Risk and evidence: The starter application container was built from `python:3.12-slim-bookworm`, which contained **282 total vulnerabilities** (5 CRITICAL, 58 HIGH, 112 MEDIUM, 103 LOW, 4 UNKNOWN), with 276 located in Debian OS base packages. Most critically, it included unpatched CRITICAL buffer overflow `CVE-2023-45853` in `zlib1g`.
- Impact: Remote attackers exploiting `zlib1g` or Debian library vulnerabilities can trigger heap-based memory corruption and execute arbitrary code within the backend container, compromising the Flask application environment.
- Implemented fix / commit:
  1. Migrated base image to `python:3.13-alpine@sha256:79e7a9b9ff1cbceff819f856fb374477792a5967759d94df266de7b7b4120e6f` (Commit `a03158d`). This eliminated all 276 OS-level vulnerabilities, bringing the total count down from 282 to just 3 (0 CRITICALs, 0 OS-level CVEs, 2 HIGH, 1 MEDIUM in Python pip packages `werkzeug` and `urllib3`).
  2. Integrated automated Trivy vulnerability scanning into `.github/workflows/ci.yml` (Commit `cf9e925`) using `aquasecurity/trivy-action`, generating SARIF security reports uploaded directly to GitHub Security Code Scanning.
  3. **CI Scanner Triage Policy (`exit-code: 0`):** In CI, the Trivy step scans `barq-app:test` with `exit-code: 0`. We deliberately do not fail the build because the remaining 3 vulnerabilities are application-layer Python package dependencies required by the starter Flask code rather than OS vulnerabilities. Failing CI on application dependencies requiring upstream application refactoring would block deployments; instead, SARIF reports are uploaded for asynchronous security triage while OS attack vectors are 100% eliminated.
- Production follow-up: Transition to Google Distroless or Chainguard Wolfi images to eliminate shells (`/bin/sh`) and package managers (`apk`) entirely from production runtime. Implement Dependabot / Renovate to automate patch pull requests for application-layer Python dependencies (`werkzeug`, `urllib3`).
- How to verify: Run `trivy image python:3.13-alpine` (confirms 0 OS-level vulnerabilities) and inspect the GitHub Security tab on the latest CI run.

---

## Finding 3: NGINX Reverse Proxy Vulnerabilities & Slim Footprint Hardening
- Risk and evidence: The starter NGINX reverse proxy image (`nginx:1.28-alpine`) contained **200 total vulnerabilities** (2 CRITICAL, 55 HIGH, 92 MEDIUM, 49 LOW, 2 UNKNOWN) across `musl`, `libcrypto3`, and NGINX HTTP/2 modules, with an uncompressed image footprint of 93.4 MB.
- Impact: As the only public-facing ingress point on host port 8080/8090, unpatched vulnerabilities in NGINX or its underlying cryptographic libraries (`libcrypto3`) expose the edge to HTTP/2 denial-of-service exploits, SSL/TLS handshake manipulation, and remote memory leakage.
- Implemented fix / commit:
  1. Upgraded NGINX to `nginx:stable-alpine3.24-slim@sha256:32463212baf0e7d91aded2e9b843a4f2b9e017804b8c9d5bae7b51dcef64389c` (Commit `6f4275c`).
  2. Achieved **0 vulnerabilities (100% clean across all severities: 0 CRITICAL, 0 HIGH, 0 MEDIUM, 0 LOW)**.
  3. Slashed container image size by 77% from 93.4 MB down to **21 MB**, radically shrinking the attack surface.
- Production follow-up: Integrate a Web Application Firewall (WAF) module (such as ModSecurity or Coraza) and configure automated TLS certificate rotation with Let's Encrypt / Cert-Manager.
- How to verify: Run `trivy image nginx:stable-alpine3.24-slim` (confirms 0 vulnerabilities across all severities).

---

## Finding 4: Redis In-Memory Cache OpenSSL Vulnerabilities
- Risk and evidence: The starter Redis release (`redis:7.4-alpine`) contained **26 total vulnerabilities** (0 CRITICAL, 2 HIGH, 10 MEDIUM, 14 LOW) in Alpine 3.21.7 base packages. Specifically, it contained 2 HIGH severity vulnerabilities in `libcrypto3` and `libssl3` (`CVE-2026-45447` OpenSSL PKCS7_verify Use-After-Free).
- Impact: Cryptographic library use-after-free vulnerabilities in `libcrypto3` allow remote attackers to cause memory corruption, potential arbitrary code execution, or server crashes during TLS sessions and cryptographic verification.
- Implemented fix / commit:
  1. Upgraded Redis base image to patch release `redis:7.4.11-alpine@sha256:858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499` on Alpine 3.21.8 (Commit `1386ef3`).
  2. Completely eliminated the OpenSSL CVEs, achieving **0 vulnerabilities (100% clean across all severities)**.
- Production follow-up: Enable Redis AUTH with a strong password or TLS client certificate authentication (`tls-auth-clients`), and configure memory limits (`maxmemory 200mb`) with eviction policies (`allkeys-lru`).
- How to verify: Run `trivy image redis:7.4.11-alpine` (confirms 0 vulnerabilities across all severities).

---

## Finding 5: PostgreSQL Base OS Vulnerabilities & Immutable Digest Pinning
- Risk and evidence: The starter PostgreSQL image digest (`postgres:16-alpine@sha256:cf78...`) was based on an outdated Alpine 3.21 build containing **74 total vulnerabilities** (1 CRITICAL, 30 HIGH, 28 MEDIUM, 14 LOW, 1 UNKNOWN), including 28 vulnerabilities located in the operating system base packages.
- Impact: Unpatched OS-level packages (including `busybox`, `libxml2`, and SSL libraries) provide initial local privilege escalation vectors and container escape footholds if an attacker compromises the PostgreSQL database process.
- Implemented fix / commit:
  1. Upgraded and pinned PostgreSQL to `postgres:16-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea` on Alpine 3.24.2 (Commit `7deed68`).
  2. Eliminated all 28 OS-level vulnerabilities, reducing total CVEs from 74 down to 46 with **0 OS-level vulnerabilities**. (The remaining 46 are PostgreSQL internal language libraries).
  3. Pinned by immutable SHA-256 digest to prevent non-deterministic upstream build drift.
- Production follow-up: Implement automated database vulnerability auditing using continuous container scanners and establish automated Write-Ahead Logging (WAL) archiving with `pgBackRest` or `wal-g`.
- How to verify: Run `trivy image postgres:16-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea` (confirms 0 OS-level vulnerabilities).

---

## Finding 6: Root Privilege Escalation & Container Escape Vulnerability (CWE-250)
- Risk and evidence: By default, Docker containers execute processes with `root` privileges (`UID 0`, `GID 0`). The starter `Dockerfile` lacked any user specification, running the Flask API server and Gunicorn workers directly as root inside the container.
- Impact: If an attacker identifies an application-level vulnerability (such as remote code execution via unsafe deserialization or file upload), running as `UID 0` grants the attacker root access within the container namespace. From there, exploiting container runtime flaws or Linux kernel vulnerabilities allows escaping to the host machine with full host root privileges.
- Implemented fix / commit:
  1. In [Dockerfile](file:///home/devops/BARQ-Academy/Dockerfile) (Commit `a03158d`), explicitly created an unprivileged system group and user with fixed IDs: `RUN addgroup -g 10001 -S app && adduser -u 10001 -S -G app -H -D app`.
  2. Assigned ownership of the application directory to the unprivileged user: `COPY --chown=app:app app/ ./app/`.
  3. Enforced unprivileged runtime execution via `USER app` directive before the entrypoint.
- Production follow-up: Enforce read-only root filesystems (`read_only: true`), drop all Linux capabilities (`cap_drop: [ALL]`), and set `securityContext.runAsNonRoot: true` in Kubernetes manifests with strict seccomp (`RuntimeDefault`) and AppArmor profiles.
- How to verify: Execute `docker compose exec app-01 id` (returns `uid=10001(app) gid=10001(app) groups=10001(app)`).

---

## Finding 7: Unauthenticated Public Host Port Exposure & Ingress Bypass
- Risk and evidence: In starter `docker-compose.yml`, PostgreSQL published host port `127.0.0.1:15432:5432` and Redis published host port `127.0.0.1:16379:6379`.
- Impact: Exposing internal database and caching ports to the host network interface allows any local unprivileged process, compromised adjacent container, or network-level attacker to bypass NGINX reverse proxy authentication, rate-limiting, and web application firewall rules. Attackers can execute unauthenticated Redis commands (potentially achieving remote code execution) or directly execute SQL queries against PostgreSQL.
- Implemented fix / commit:
  1. Removed all `ports:` directives from `postgres`, `redis`, and backend `app` containers in `docker-compose.yml` (Commit `fd64c2e`).
  2. Restricted host port binding strictly to NGINX on `127.0.0.1:${PUBLIC_PORT:-8080}:80`.
- Production follow-up: Enforce host-level Linux firewalls (`iptables` / `ufw`), utilize Cloud Security Groups, and run all internal microservices in private subnets with zero public ingress.
- How to verify: Run `python3 validate.py` — passes 4/4 prohibited host port checks (`PASS: container: postgres has no host port`, `redis has no host port`, `app-01 has no host port`, `app-02 has no host port`).

---

## Finding 8: Flat Network Topology & Lateral Movement Vulnerability
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

## Finding 9: Ephemeral Container Storage & Lack of Automated Disaster Recovery (Persistence / Backup)
- Risk and evidence: In the starter stack, `postgres` and `redis` did not declare persistent named volume mounts (`docker-compose.yml` had no `volumes:` for database data directories `/var/lib/postgresql/data` and `/data`). Database and caching state were written directly into the containers' ephemeral writable layers. Executing `docker compose down` or recreating containers caused permanent data loss. Furthermore, the repository lacked any automated backup or restore mechanism to protect against accidental data corruption or host failure.
- Impact: Complete, irreversible loss of production data, customer records, and operational state upon container recreation or node restarts. High Recovery Time Objective (RTO = infinity) and Recovery Point Objective (RPO = infinity) due to absent recovery procedures.
- Implemented fix / commit:
  1. Configured persistent named volumes `postgres-data` and `redis-data` (Commit `7deed68` and `1386ef3`), mapping `/var/lib/postgresql/data` and `/data` to preserve data across container lifecycles.
  2. Enabled Redis Append-Only File (AOF) persistence (`--appendonly yes`) on persistent volume `redis-data` to log all write operations to disk.
  3. Authored [`backup.sh`](file:///home/devops/BARQ-Academy/backup.sh) and [`restore.sh`](file:///home/devops/BARQ-Academy/restore.sh) with end-to-end automated verification, testing that data survives complete container destruction and re-creation.
  4. Restricted backup directory permissions on creation (`mkdir -p backups && chmod 700 backups`).
- Production follow-up (Features Not Implemented):
  1. **Feature Not Implemented — Cryptographic Backup Encryption at Rest (CWE-311):** Current backups are written as raw plaintext SQL dumps (`backups/*.sql`). Automated encryption at rest using AES-256 (via OpenSSL or GPG asymmetric key pairs) is not implemented in the current local stack and is planned for production deployment before storing archives on shared or remote filesystems.
  2. **Feature Not Implemented — Offsite Immutable Cloud Replication & PITR:** Current backups reside strictly on the local host filesystem. Offsite replication to immutable cloud object storage (e.g., AWS S3 with Object Lock or GCP Cloud Storage with Bucket Lock/Retention Policy) and automated Point-In-Time Recovery (PITR) with Write-Ahead Logging (`pgBackRest` / `wal-g`) are planned for enterprise production.
- How to verify:
  1. Run `./backup.sh && ./restore.sh` (confirms test record `'backup-proof'` survives container destruction and is restored with 100% integrity).
  2. Verify plaintext backup status (confirming encryption is not yet implemented): run `file backups/backup_*.sql` (shows `ASCII text` / SQL script).

---

## Finding 10: Application-Layer Denial of Service (DoS) & Slowloris Vulnerability (CWE-400)
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
