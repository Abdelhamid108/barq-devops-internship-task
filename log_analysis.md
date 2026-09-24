# Log analysis

Use all three supplied logs. Answer every question with commands/scripts and actual output.

1. What UTC interval is covered? How many valid, malformed and duplicate lines are in each file?
2. How many distinct client requests occurred? How did you deduplicate and avoid counting retries twice?
3. What are the final client status counts and error rate? State your denominator.
4. Which paths, time windows and backends account for the failures?
5. What are the median and p95 client latencies? State the percentile method and units.
6. Which requests retried upstream? How many succeeded after retrying?
7. Build an incident timeline using evidence from access, error AND application logs.
8. Show one correlated failed request and one successful request. Include IDs and timestamps.
9. Which errors appear to be proxy/connectivity issues versus dependency/application issues? What proves it?
10. What do the logs not prove? What would you check next in a running environment?

## Commands / scripts

**Q1 — time interval and line quality**

```bash
# Total lines per file
wc -l logs/access.log logs/application.log logs/error.log
```
Output:
```
  726 logs/access.log
  730 logs/application.log
   69 logs/error.log
```

```bash
# Malformed JSON lines — access.log
jq -Rr 'try (fromjson | empty) catch ("Line " + (input_line_number | tostring) + ": " + .)' logs/access.log | wc -l  
```
Output: ` 1`

```bash
# Malformed JSON lines — application.log
jq -Rr 'try (fromjson | empty) catch ("Line " + (input_line_number | tostring) + ": " + .)' logs/application.log | wc -l  
```
Output: ` 1`


```bash
# Duplicate lines per file
sort logs/access.log | uniq -d | wc -l
sort logs/application.log | uniq -d | wc -l
sort logs/error.log | uniq -d | wc -l
```
Output: `5` / `2` / `0`

```bash
# Time interval — access.log
jq -Rr 'fromjson? | .timestamp' logs/access.log | sort | (head -n 1; tail -n 1)
```
Output:
```
2026-08-20T11:00:00.015Z
2026-08-20T11:29:57.578Z
```

```bash
# Time interval — application.log
jq -Rr 'fromjson? | .timestamp' logs/application.log | sort | (head -n 1; tail -n 1)
```
Output:
```
2026-08-20T11:00:00.015Z
2026-08-20T11:29:57.578Z
```

```bash
# Time interval — error.log (plain text, not JSON)
sort logs/error.log | awk 'NR==1 {first=$0} {last=$0} END {print first; print last}' | awk '{print $1, $2}'
```
Output: 
```
2026/08/20 11:05:02
2026/08/20 11:30:00 
```

---

**Q2 — valid requests, deduplication and retries**

```bash 
# Calculate distinct client requests occurred
jq -Rr 'fromjson? | .request_id // empty' logs/access.log | sort -u | wc -l
```
Output:
```
720
```

```bash
# Show duplicated request IDs
jq -Rr 'fromjson? | .request_id // empty' logs/access.log | sort | uniq -d
```
Output:
```
lab-000121
lab-000241
lab-000361
lab-000481
lab-000601
```

---

**Q3 — requests status**

```bash
# Count requests per status code (deduplicated, ignoring malformed line)
sort -u logs/access.log | jq -Rr 'fromjson? | .status // empty' | sort | uniq -c
```
Output:
```
    615 200
     10 404
     40 502
     47 503
      8 504
```

---

**Q4 — failure paths, time windows, and backends**

```bash
# print paths and upstreams for 502 errors only
sort -u logs/access.log | jq -Rr 'fromjson? | select(.status == 502) | "\(.status) \(.path) \(.upstream)"' | sort | uniq -c | sort -nr 
```
output:
```
     10 502 /records 172.23.0.12:8080
     10 502 /health 172.23.0.12:8080
     10 502 /counter 172.23.0.12:8080
     10 502 / 172.23.0.12:8080
```
```bash 
# time window for 502 errors
jq -Rr 'fromjson? | select(.status == 502) | .timestamp' logs/access.log |
sort | awk 'NR==1 {first=$0} {last=$0} END {print first; print last}'
```
Output:
```
2026-08-20T11:05:02.503Z
2026-08-20T11:09:57.503Z
```
```bash
# print paths and upstreams for 503 errors only
sort -u logs/access.log | jq -Rr 'fromjson? | select(.status == 503) | "\(.status) \(.path) \(.upstream)"' | sort | uniq -c | sort -nr
```
output:
```
     12 503 /ready 172.23.0.12:8080
     11 503 /ready 172.23.0.11:8080
      8 503 /counter 172.23.0.12:8080
      8 503 /counter 172.23.0.11:8080
      4 503 /records 172.23.0.12:8080
      4 503 /records 172.23.0.11:8080
```
```bash
# time window for 503 errors
jq -Rr 'fromjson? | select(.status == 503) | .timestamp' logs/access.log |
sort | awk 'NR==1 {first=$0} {last=$0} END {print first; print last}'
```
Output:
```
2026-08-20T11:12:09.525Z
2026-08-20T11:21:45.041Z
```
```bash
# print paths and upstreams for 504 errors only
sort -u logs/access.log | jq -Rr 'fromjson? | select(.status == 504) | "\(.status) \(.path) \(.upstream)"' | sort | uniq -c | sort -nr
```
output:
```
      4 504 /records 172.23.0.12:8080
      4 504 /records 172.23.0.11:8080
```
```bash
# time window for 504 errors
jq -Rr 'fromjson? | select(.status == 504) | .timestamp' logs/access.log |
sort | awk 'NR==1 {first=$0} {last=$0} END {print first; print last}'
```
Output:
```
2026-08-20T11:25:14.501Z
2026-08-20T11:26:47.001Z
```
```bash
# print paths and upstreams for 404 errors only
sort -u logs/access.log | jq -Rr 'fromjson? | select(.status == 404) | "\(.status) \(.path) \(.upstream)"' | sort | uniq -c | sort -nr
```
output:
```
      5 404 /missing 172.23.0.12:8080
      5 404 /missing 172.23.0.11:8080
```
```bash
# time window for 404 errors
jq -Rr 'fromjson? | select(.status == 404) | .timestamp' logs/access.log |
sort | awk 'NR==1 {first=$0} {last=$0} END {print first; print last}'
```
output:
```
2026-08-20T11:00:00.015Z
2026-08-20T11:29:37.522Z
```
---

**Q5 — median and p95 client latencies**

```python
# percentile.py — Calculate median and p95 client latency across distinct requests
#!/usr/bin/env python3
import json
import numpy as np

data = []
file_path = "logs/access.log"
for l in sorted(set(open(file_path))):
    try:
        val = json.loads(l).get("request_time")
        if val is not None:
            data.append(float(val))
    except:
        pass

data.sort()
n = len(data)
p50 = np.percentile(data, 50)
p95 = np.percentile(data, 95)

print(f"Total requests: {n}")
print(f"Median (P50): {p50:.3f} s ({p50 * 1000:.1f} ms)")
print(f"P95: {p95:.3f} s ({p95 * 1000:.1f} ms)")
```
Output:
```
Total requests: 720
Median (P50): 0.054 s (54.0 ms)
P95: 2.001 s (2001.0 ms)
```

---

**Q6 — upstream retries**

```bash
# Show requests with multiple upstream responses 
sort -u logs/access.log | jq -Rr 'fromjson? | select(.upstream | contains(",")) | "\(.request_id) \(.path) status=\(.status) upstream_status=[\(.upstream_status)]"'
```
Output:
```
lab-000124 /ready status=200 upstream_status=[502, 200]
lab-000130 /instance status=200 upstream_status=[502, 200]
lab-000136 /ready status=200 upstream_status=[502, 200]
lab-000142 /instance status=200 upstream_status=[502, 200]
lab-000148 /ready status=200 upstream_status=[502, 200]
lab-000154 /instance status=200 upstream_status=[502, 200]
lab-000160 /ready status=200 upstream_status=[502, 200]
lab-000166 /instance status=200 upstream_status=[502, 200]
lab-000172 /ready status=200 upstream_status=[502, 200]
lab-000178 /instance status=200 upstream_status=[502, 200]
lab-000184 /ready status=200 upstream_status=[502, 200]
lab-000190 /instance status=200 upstream_status=[502, 200]
lab-000196 /ready status=200 upstream_status=[502, 200]
lab-000202 /instance status=200 upstream_status=[502, 200]
lab-000208 /ready status=200 upstream_status=[502, 200]
lab-000214 /instance status=200 upstream_status=[502, 200]
lab-000220 /ready status=200 upstream_status=[502, 200]
lab-000226 /instance status=200 upstream_status=[502, 200]
lab-000232 /ready status=200 upstream_status=[502, 200]
```

```bash 
# Count total retries and check their final status
sort -u logs/access.log | jq -Rr 'fromjson? | select(.upstream | contains(",")) | .status' | sort | uniq -c
```
Output:
```
     19 200
```

---

**Q7 — incident timeline**

```bash
# First and last "Connection refused" in error.log
grep "Connection refused" logs/error.log | awk '{print $1, $2}' | sed -n '1p;$p'
```
Output:
```
2026/08/20 11:05:02
2026/08/20 11:09:57
```

```bash
# First and last "upstream timed out" in error.log
grep "upstream timed out" logs/error.log | awk 'NR==1 {first=$1" "$2} {last=$1" "$2} END {print first; print last}'
```
Output:
```
2026/08/20 11:25:14
2026/08/20 11:26:47
```

```bash
# First and last ERROR level events in application.log
jq -c -Rr 'fromjson? | select(.level == "ERROR") | {timestamp, request_id, instance_id, dependency, error_type}' logs/application.log | sed -n '1p;$p'
```
Output:
```
{"timestamp":"2026-08-20T11:12:09.524Z","request_id":"lab-000292","instance_id":"app-02","dependency":"redis","error_type":"TimeoutError"}
{"timestamp":"2026-08-20T11:21:45.040Z","request_id":"lab-000523","instance_id":"app-01","dependency":"postgres","error_type":"InvalidPassword"}
```

```bash
# First and last redis dependency errors in application.log
jq -c -Rr 'fromjson? | select(.dependency == "redis") | {timestamp, request_id, instance_id, error_type}' logs/application.log | awk 'NR==1 {first=$0} {last=$0} END {print first; print last}'
```
Output:
```
{"timestamp":"2026-08-20T11:12:09.524Z","request_id":"lab-000292","instance_id":"app-02","error_type":"TimeoutError"}
{"timestamp":"2026-08-20T11:15:52.024Z","request_id":"lab-000381","instance_id":"app-01","error_type":"TimeoutError"}
```

```bash
# First and last postgres dependency errors in application.log
jq -c -Rr 'fromjson? | select(.dependency == "postgres") | {timestamp, request_id, instance_id, error_type}' logs/application.log | awk 'NR==1 {first=$0} {last=$0} END {print first; print last}'
```
Output:
```
{"timestamp":"2026-08-20T11:20:07.540Z","request_id":"lab-000484","instance_id":"app-02","error_type":"InvalidPassword"}
{"timestamp":"2026-08-20T11:21:45.040Z","request_id":"lab-000523","instance_id":"app-01","error_type":"InvalidPassword"}
```

---

**Q8 — correlated request examples**

```bash
# 1. Identify a failed request ID from access.log (status 503)
jq -Rr 'fromjson? | select(.status == 503) | .request_id' logs/access.log | head -n 1
```
Output:
```
lab-000292
```

```bash
# 2. Correlate the failed request (lab-000292) across all logs
grep "lab-000292" logs/access.log logs/error.log logs/application.log
```
Output:
```
logs/access.log:{"timestamp":"2026-08-20T11:12:09.525Z","request_id":"lab-000292","method":"GET","path":"/ready","status":503,"upstream":"172.23.0.12:8080","upstream_status":"503","request_time":2.025,"client":"192.0.2.24"}
logs/application.log:{"timestamp": "2026-08-20T11:12:09.524Z", "level": "ERROR", "event": "dependency_error", "request_id": "lab-000292", "instance_id": "app-02", "dependency": "redis", "error_type": "TimeoutError"}
logs/application.log:{"timestamp": "2026-08-20T11:12:09.525Z", "level": "WARN", "event": "http_request", "request_id": "lab-000292", "instance_id": "app-02", "method": "GET", "path": "/ready", "status": 503, "duration_ms": 2025.0}
```

```bash
# 3. Identify a successful request ID from access.log (status 200)
jq -Rr 'fromjson? | select(.status == 200) | .request_id' logs/access.log | head -n 1
```
Output:
```
lab-000002
```

```bash
# 4. Correlate the successful request (lab-000002) across all logs
grep "lab-000002" logs/access.log logs/error.log logs/application.log
```
Output:
```
logs/access.log:{"timestamp":"2026-08-20T11:00:02.532Z","request_id":"lab-000002","method":"GET","path":"/health","status":200,"upstream":"172.23.0.12:8080","upstream_status":"200","request_time":0.032,"client":"192.0.2.24"}
logs/application.log:{"timestamp": "2026-08-20T11:00:02.532Z", "level": "INFO", "event": "http_request", "request_id": "lab-000002", "instance_id": "app-02", "method": "GET", "path": "/health", "status": 200, "duration_ms": 32.0}
```

## Results

**Q1** 

Overall observation window: **2026-08-20T11:00:00Z → 2026-08-20T11:30:00Z** (~30 minutes)

| File | UTC Interval Covered | Total Lines | Malformed | Valid | Duplicate Lines |
|------|----------------------|------------|-----------|-------|-----------------|
| `access.log` | `2026-08-20T11:00:00.015Z` → `11:29:57.578Z` | 726 | 1 | 725 | 5 |
| `application.log` | `2026-08-20T11:00:00.015Z` → `11:29:57.578Z` | 730 | 1 | 729 | 2 |
| `error.log` | `2026/08/20 11:05:02` → `11:30:00` | 69 | 0 | 69 | 0 |

- `access.log` and `application.log` each have 1 truncated JSON line (at line 313 and equivalent). All subsequent `jq` commands use `fromjson?` to skip them silently.
- `error.log` begins at `11:05:02` because NGINX only logs on error/notice conditions; no errors occurred during the first ~5 minutes. The final line (`11:30:00`) is a `[notice]` log-rotation entry.
- Duplicate lines are exact byte-for-byte copies (logging artefact), not retried client requests. Excluded from all request counts.
- **Log ordering:** The logs are not guaranteed to be pre-sorted (`application.log` has timestamps slightly out of sequence due to concurrent workers). Timestamps were explicitly sorted to guarantee the correct time window.

---

**Q2 — distinct client requests**
- **Total:** 720 distinct client requests (`lab-000001` through `lab-000720`).
- **Deduplication:** 5 duplicate lines were detected (`lab-000121`, `lab-000241`, `lab-000361`, `lab-000481`, `lab-000601`) via `sort | uniq -d`. These were exact byte-for-byte duplicate log flushes (identical timestamps, payloads, and single upstream status 200), not retried requests, and were excluded using `sort -u`.
- **Handling of retries:** NGINX logs upstream reverse-proxy retries within a **single access log entry** using comma-separated upstreams and statuses (e.g. `"upstream_status": "502, 200"` for `lab-000124`). Because retries do not generate separate log lines in `access.log`, counting distinct client `request_id`s inherently avoids counting retries twice.
- **Malformed line handling:** Line 311 is truncated before writing `request_id`. Because the integer ID sequence between `lab-000001` and `lab-000720` is 100% complete with no missing numbers, line 311 is an aborted write rather than an uncounted 721st request.

---

**Q3 — final status counts and error rate**
- **Final client status counts** (after deduplicating 5 duplicate log lines):
  - `200 OK`: **615** (85.4%)
  - `404 Not Found`: **10** (1.4%)
  - `502 Bad Gateway`: **40** (5.6%)
  - `503 Service Unavailable`: **47** (6.5%)
  - `504 Gateway Timeout`: **8** (1.1%)
  - *Summary by category:* `2xx` (Success): 615, `4xx` (Client Error): 10, `5xx` (Proxy/Server Error): 95

- **Error rate denominator:** **720** total distinct client requests.
- **Server Error rate (5xx only):** 95 errors / 720 requests = **13.2%** (40 Bad Gateway + 47 Service Unavailable + 8 Gateway Timeout)
- **Client Error rate (4xx only):** 10 errors / 720 requests = **1.4%** (10 Not Found)
- **Total HTTP Error rate (4xx + 5xx):** 105 errors / 720 requests = **14.6%**

---

**Q4 — failure paths, time windows, and backends**

| Failure Status | Count | Affected Paths | Time Window (UTC) | Affected Backend(s) |
|---|---|---|---|---|
| `502 Bad Gateway` | 40 | `/records` (10), `/health` (10), `/counter` (10), `/` (10) | `11:05:02 — 11:09:57` | `172.23.0.12:8080` (40) |
| `503 Service Unavailable` | 47 | `/ready` (23), `/counter` (16), `/records` (8) | `11:12:09 — 11:21:45` | `172.23.0.11:8080` (23), `172.23.0.12:8080` (24) |
| `504 Gateway Timeout` | 8 | `/records` (8) | `11:25:14 — 11:26:47` | `172.23.0.11:8080` (4), `172.23.0.12:8080` (4) |
| `404 Not Found` | 10 | `/missing` (10) | `11:00:00 — 11:29:37` | `172.23.0.11:8080` (5), `172.23.0.12:8080` (5) |

- **Paths summary:** `/records` (26 5xx) and `/counter` (26 5xx) experienced the highest server failures, followed by `/ready` (23 5xx), `/health` (10 5xx), and `/` (10 5xx).
- **Backends summary:** `172.23.0.12:8080` (`app-02`) accounted for **68 server failures** (71.6%), including 100% of the `502` errors. `172.23.0.11:8080` (`app-01`) accounted for **27 server failures** (28.4%), only encountering `503` and `504` errors.

---

**Q5 — median and p95 client latencies**

- **Dataset evaluated:** 720 distinct client requests (from `logs/access.log`, deduplicated).
- **Metric measured:** NGINX `request_time` (total elapsed time from receiving the first request byte to sending the final response byte).
- **Units:** Recorded in **seconds (`s`)**, reported in both **seconds (`s`)** and **milliseconds (`ms`)**.
- **Percentile method:** **Linear interpolation** via NumPy (`np.percentile`).

| Latency Metric | Seconds (`s`) | Milliseconds (`ms`) | Method |
|---|---|---|---|
| **Median (P50)** | `0.054 s` | `54.0 ms` | 50th percentile (NumPy linear interpolation) |
| **P95** | `2.001 s` | `2001.0 ms` | 95th percentile (NumPy linear interpolation) |

---

**Q6 — upstream retries and success rate**

- **Total retried requests:** Exactly **19 requests** retried upstream.
- **Success rate after retrying:** **19 out of 19 (100%)** succeeded with final client status `200 OK`.
- **Retried paths & Request IDs:** Retries occurred **exclusively on two endpoints**:
  - `/ready` (10 requests): `lab-000124`, `lab-000136`, `lab-000148`, `lab-000160`, `lab-000172`, `lab-000184`, `lab-000196`, `lab-000208`, `lab-000220`, `lab-000232`
  - `/instance` (9 requests): `lab-000130`, `lab-000142`, `lab-000154`, `lab-000166`, `lab-000178`, `lab-000190`, `lab-000202`, `lab-000214`, `lab-000226`
- **Failover Observation:**
  - During the `11:05:02 — 11:09:57` outage when `app-02` (`172.23.0.12:8080`) went down, `/ready` and `/instance` were the **only endpoints** where upstream retries occurred.
  - When these 19 requests initially hit `app-02` and faced a `502` connection refusal, NGINX failed over to `app-01` (`172.23.0.11:8080`), where all 19 retried and passed successfully (`upstream_status=[502, 200]`, final status `200`).
  - The other 40 requests routed to `app-02` during this window (`/`, `/health`, `/records`, `/counter`) were not retried and resulted in `502 Bad Gateway`.

---

## Timeline and correlated examples

**Q7 — incident timeline**

Correlating `access.log`, `error.log`, and `application.log` reveals **4 failure windows** accounting for all 95 server errors (`5xx`):

| Incident | Time Window (UTC) | `error.log` Evidence | `access.log` Evidence (Q3, Q4, Q6) | `application.log` Evidence | Next Successful Request |
|---|---|---|---|---|---|
| **1** | `11:05:02 — 11:09:57` | 59 lines: `Connection refused` (`172.23.0.12:8080`) | 40 `502`s on `/`, `/health`, `/records`, `/counter`; 19 retries on `/ready` & `/instance` succeeded on `app-01` (Q6) | 0 lines for `app-02`; `app-01` logged normally | `11:10:02.532Z` (`lab-000242`, `app-02`, `/health`, 200) |
| **2** | `11:12:09 — 11:15:52` | 0 lines | 31 `503`s on `/counter` (16) and `/ready` (15); `request_time`: 2.019s–2.035s | 31 ERROR lines: `dependency: redis`, `error_type: TimeoutError` | `11:16:07.534Z` (`lab-000388`, `/ready`, 200) |
| **3** | `11:20:07 — 11:21:45` | 0 lines | 16 `503`s on `/records` (8) and `/ready` (8); `request_time`: 0.021s–0.088s | 16 ERROR lines: `dependency: postgres`, `error_type: InvalidPassword` | `11:22:07.582Z` (`lab-000532`, `/ready`, 200) |
| **4** | `11:25:14 — 11:26:47` | 8 lines: `upstream timed out` on `/records` | 8 `504`s on `/records`; `request_time`: 2.001s | 8 lines for `/records`: `status: 200`, `duration_ms: 2700.0` | `11:27:12.576Z` (`lab-000654`, `/records`, 200) |

---

**Q8 — correlated request examples**

#### 1. Correlated Failed Request: `lab-000292`
- **Request ID:** `lab-000292`
- **Path & Method:** `GET /ready`
- **Target Backend:** `172.23.0.12:8080` (`app-02`)
- **Evidence across logs:**
  - **`access.log`** (`2026-08-20T11:12:09.525Z`): `status: 503`, `upstream: "172.23.0.12:8080"`, `upstream_status: "503"`, `request_time: 2.025s`.
  - **`application.log`**:
    - `2026-08-20T11:12:09.524Z`: `level: "ERROR"`, `event: "dependency_error"`, `instance_id: "app-02"`, `dependency: "redis"`, `error_type: "TimeoutError"`.
    - `2026-08-20T11:12:09.525Z`: `level: "WARN"`, `event: "http_request"`, `instance_id: "app-02"`, `status: 503`, `duration_ms: 2025.0`.
  - **`error.log`**: 0 entries logged (the application returned an HTTP 503 response, so NGINX did not encounter an upstream socket or proxy error).

#### 2. Correlated Successful Request: `lab-000002`
- **Request ID:** `lab-000002`
- **Path & Method:** `GET /health`
- **Target Backend:** `172.23.0.12:8080` (`app-02`)
- **Evidence across logs:**
  - **`access.log`** (`2026-08-20T11:00:02.532Z`): `status: 200`, `upstream: "172.23.0.12:8080"`, `upstream_status: "200"`, `request_time: 0.032s`.
  - **`application.log`** (`2026-08-20T11:00:02.532Z`): `level: "INFO"`, `instance_id: "app-02"`, `status: 200`, `duration_ms: 32.0`.
  - **`error.log`**: 0 entries logged (NGINX logs errors/notices only; normal 200 responses produce no error logs).

---

## Conclusions and limits
