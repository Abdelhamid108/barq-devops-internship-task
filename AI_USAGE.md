# AI usage disclosure

Write None if no AI was used. Otherwise record each use:

- Tool/model:
- Purpose:
- Files or decisions affected:
- What you changed or rejected:
- How you independently verified it:

You may use AI and external resources. You must understand and demonstrate the work.

---

## Use 1: Historical Log Analysis & Command Syntax
- Tool/model: Antigravity AI Assistant (Google Gemini 3.8, Claude 4.6 Sonnet)
- Purpose: Helping formulate query syntax (`jq`, `awk`, and shell pipes) to analyze the three historical log files (`logs/access.log`, `logs/application.log`, and `logs/error.log`) and drafting the answers to the 10 analysis questions in `log_analysis.md`.
- Files or decisions affected: [`log_analysis.md`](file:///home/devops/BARQ-Academy/log_analysis.md).
- What you changed or rejected: AI initially proposed a single monolithic script to extract all analysis points in one pass. I rejected this all-in-one script and requested simple, standalone, and easily reproducible Linux CLI commands for each individual question so they could be executed directly in the terminal. The AI then assisted with the syntax for those individual commands (`jq` filters, regex matching, percentile extractions), which I reviewed, adapted, and applied to systematically answer each section of `log_analysis.md`.
- How you independently verified it: Executed each simple reproducible command manually in the Linux shell across the 3 log files, validated that terminal outputs matched the raw log contents, confirmed counts against baseline file lines (`wc -l`), and committed the verified findings progressively question by question.

---

## Use 2: Test Automation & Failure Resilience
- Tool/model: Antigravity AI Assistant (Google Gemini 3.8, Claude 4.6 Sonnet)
- Purpose: Assisting with command logic, Docker CLI inspection, and HTTP request/assertion logic for the environment validation suite and failure resiliency tests ([`validate.py`](file:///home/devops/BARQ-Academy/validate.py) and [`failure_test.py`](file:///home/devops/BARQ-Academy/failure_test.py)).
- Files or decisions affected: [`validate.py`](file:///home/devops/BARQ-Academy/validate.py), [`failure_test.py`](file:///home/devops/BARQ-Academy/failure_test.py).
- What you changed or rejected: AI initially provided flat, monolithic scripts without modular functions or structured separation. I rejected this monolithic design and re-architected the solution using Python to apply SOLID principles (Single Responsibility and Separation of Concerns). I structured the codebase by separating responsibilities into clean layers: an execution/data layer for Docker inspection and HTTP calls, a validation/logic layer for health and network assertions, and a presentation layer for deterministic PASS/FAIL console reporting. In `failure_test.py`, I rejected open-ended polling loops and enforced a deterministic 10-request measurement routine during the `app-01` outage (capturing exact 30% availability) and 10 requests post-recovery (verifying 100% availability).
- How you independently verified it: Executed each script end-to-end in the terminal: `validate.py` passed 21/21 assertions across endpoints, load balancing, health, network isolation, and host ports; and `failure_test.py` verified fail-fast NGINX routing and service recovery.

---

## Use 3: Disaster Recovery & Persistence Automation
- Tool/model: Antigravity AI Assistant (Google Gemini 3.8, Claude 4.6 Sonnet)
- Purpose: Assisting with shell command syntax for PostgreSQL dump/restore execution and automated container lifecycle recreation scripts ([`backup.sh`](file:///home/devops/BARQ-Academy/backup.sh) and [`restore.sh`](file:///home/devops/BARQ-Academy/restore.sh)).
- Files or decisions affected: [`backup.sh`](file:///home/devops/BARQ-Academy/backup.sh), [`restore.sh`](file:///home/devops/BARQ-Academy/restore.sh).
- What you changed or rejected: AI initially suggested using static `sleep` delays to wait for containers during recreation; I rejected static timers and replaced them with bounded polling against the application `/ready` health endpoint (`wait_for_ready()`). I also structured the procedural shell logic into modular, reusable Bash functions (`create_record`, `check_record_exists`, `create_sql_backup`, `recreate_containers`, `delete_existing_database`, `restore_database`) with strict error handling (`set -euo pipefail`).
- How you independently verified it: Executed `./backup.sh` and `./restore.sh` locally: confirmed test record `'test-eval-rec'` survived complete container destruction (`docker compose down && docker compose up -d`), verified schema was cleared, and confirmed data was restored from the SQL dump with 100% record integrity.

---

## Use 4: Container Image Selection & Runtime Verification
- Tool/model: Antigravity AI Assistant (Google Gemini 3.8, Claude 4.6 Sonnet)
- Purpose: Evaluating base image alternatives, analyzing CVE vulnerability metrics, and verifying runtime compatibility after switching base images.
- Files or decisions affected: [`Dockerfile`](file:///home/devops/BARQ-Academy/Dockerfile), [`docker-compose.yml`](file:///home/devops/BARQ-Academy/docker-compose.yml), [`decisions.md`](file:///home/devops/BARQ-Academy/decisions.md) (Decisions 1–4).
- What you changed or rejected: The AI initially only proposed changing the base images for the Flask app and NGINX, leaving PostgreSQL and Redis untouched. Furthermore, the AI cautioned against using `nginx:stable-alpine3.24-slim`, incorrectly claiming it would lack `wget` or required health-check utilities. I rejected this advice after verifying that the slim Alpine image indeed provides necessary health-check utilities while achieving a clean 21 MB footprint and 0 CVEs. I also took the initiative to identify more secure, patched upstream releases for the remaining services (`redis:7.4.11-alpine` patching OpenSSL use-after-free flaws, and `postgres:16-alpine@sha256:7218...` eliminating 28 base OS CVEs). The AI then assisted with verifying and testing that the application cleanly built and functioned properly (validating that `psycopg[binary]` installed and ran without glibc issues, and confirming all container health checks passed) right after the image migrations.
- How you independently verified it: Built the new images locally, inspected container health checks (`wget -q --spider http://127.0.0.1:80/health`), verified 0 OS-level vulnerabilities via `trivy image`, ran the test suite, and confirmed the application functioned without errors immediately after changing the images.

---

## Use 5: Code Implementation, Documentation Refinement & Complexity Reduction
- Tool/model: Antigravity AI Assistant (Google Gemini 3.8, Claude 4.6 Sonnet)
- Purpose: All-around programming assistance, typing and refining Markdown documentation (`.md` reports), suggesting manual testing commands, and proposing configuration structures.
- Files or decisions affected: [`troubleshooting.md`](file:///home/devops/BARQ-Academy/troubleshooting.md), [`decisions.md`](file:///home/devops/BARQ-Academy/decisions.md), [`docker-compose.yml`](file:///home/devops/BARQ-Academy/docker-compose.yml), and project configuration files.
- What you changed or rejected: The AI consistently tended to overcomplicate things—introducing excessive code abstraction, overly verbose explanations, and convoluted workflows. I critically reviewed all generated output and actively researched simpler, cleaner ways to implement the required functionality. Wherever the AI suggested over-engineered patterns or bloated documentation details, I aggressively stripped out the noise and deleted unnecessary complexity. For instance, in `decisions.md`, I rejected mixed CVE matrices and simplified entries to focus strictly on actionable architectural choices; in Compose configurations, I ensured minimal and readable directives.
- How you independently verified it: Manually tested every suggested CLI command and container setting in the live environment, compared code and documentation diffs against the assessment requirements, verified that simplified logic behaved identically or superior to complex alternatives, and confirmed zero unnecessary dependencies were added.

---

## Use 6: Security Vulnerability Review & Triage Policy
- Tool/model: Antigravity AI Assistant (Google Gemini 3.8, Claude 4.6 Sonnet)
- Purpose: Organizing the security review across required categories (secrets, ports, container user, image selection, networks, persistence/backup, availability) and documenting the CI vulnerability triage policy.
- Files or decisions affected: [`security_review.md`](file:///home/devops/BARQ-Academy/security_review.md), [`.github/workflows/ci.yml`](file:///home/devops/BARQ-Academy/.github/workflows/ci.yml).
- What you changed or rejected: I required separating each container image into its own distinct vulnerability finding with exact CVE counts (Findings 2–5). In CI, I rejected failing builds on application-layer pip dependencies, formulating a documented triage policy (`exit-code: 0` with SARIF upload) while ensuring 100% clean OS layers. In Finding 9, AI initially titled the finding "Unencrypted Database Backups" while the implemented fix resolved ephemeral storage; I rejected this mismatch and restructured Finding 9 to address Ephemeral Container Storage & Data Loss, while explicitly classifying cryptographic backup encryption at rest as an unimplemented feature planned for production.
- How you independently verified it: Ran `validate.py` to confirm network microsegmentation (5/5) and host port isolation (4/4), ran `trivy` scans, and confirmed GitHub Actions Code Scanning successfully ingested the SARIF security report.
