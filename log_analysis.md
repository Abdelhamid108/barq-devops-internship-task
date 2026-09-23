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

## Results

**Q1 — UTC Interval and Line Quality**

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

## Timeline and correlated examples

## Conclusions and limits
