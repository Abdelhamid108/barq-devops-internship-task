# Troubleshooting journal

Keep chronological entries. Copy this block for each meaningful investigation.

## Entry 01 - 22/09/2026 / 9:18 AM: Application Containers Reporting Unhealthy Status
- Symptom: Upon running the initial Docker Compose environment, application containers `app-01` and `app-02` reported an `(unhealthy)` status, while `postgres` and `redis` were `(healthy)`.
- Hypothesis: The Flask application failed to start or crashed on startup; logs need to be inspected to determine the failure reason.
- Command or test:
  ```bash
  docker compose -p barq-assessment ps
  ```
- Actual output:
  ```text
  NAME       IMAGE                                                                                        COMMAND                  SERVICE    CREATED          STATUS                      PORTS
  app-01     barq-assessment-app-01                                                                       "python -m app.server"   app-01     11 minutes ago   Up 10 minutes (unhealthy)   8080/tcp
  app-02     barq-assessment-app-02                                                                       "python -m app.server"   app-02     11 minutes ago   Up 10 minutes (unhealthy)   8080/tcp
  nginx      nginx:1.28-alpine@sha256:a8b39bd9cf0f83869a2162827a0caf6137ddf759d50a171451b335cecc87d236    "/docker-entrypoint.…"   nginx      5 hours ago      Up 10 minutes               80/tcp, 127.0.0.1:8080->81/tcp
  postgres   postgres:16-alpine@sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685   "docker-entrypoint.s…"   postgres   5 hours ago      Up 10 minutes (healthy)     5432/tcp
  redis      redis:7.4-alpine@sha256:ff02b58f971e7d7d156a1267e283fcbbeee91773b6aa36c49dac28ecfe28eadf     "docker-entrypoint.s…"   redis      5 hours ago      Up 10 minutes (healthy)     6379/tcp
  ```
- Failed attempt and what changed your thinking: Initially suspected the application crashed due to an unhandled runtime error. However, inspecting the container logs revealed the Flask server was running and actively responding with HTTP 404 to `/healthz`. Checking the application code and running the unit test suite (`python -m unittest discover -s tests -v`) confirmed all unit tests passed and verified that the application exposes `/health` for liveness rather than `/healthz`.
- Root cause: Configuration mismatch in `docker-compose.yml`. The `x-app` healthcheck definition targeted `http://127.0.0.1:8080/healthz`, which returned HTTP 404.Docker's healthcheck failed consecutively and marked `app-01` and `app-02` unhealthy.
- Fix: Corrected the healthcheck URL in `docker-compose.yml` under `x-app` from `http://127.0.0.1:8080/healthz` to `http://127.0.0.1:8080/health`.
- Retest evidence:
  ```bash
  docker compose -p barq-assessment ps app-01 app-02
  ```
  ```text
  NAME      IMAGE                    COMMAND                  SERVICE   CREATED          STATUS                    PORTS
  app-01    barq-assessment-app-01   "python -m app.server"   app-01    14 seconds ago   Up 13 seconds (healthy)   8080/tcp
  app-02    barq-assessment-app-02   "python -m app.server"   app-02    14 seconds ago   Up 13 seconds (healthy)   8080/tcp
  ```
- Related commit: `8ce127d` (`fix(compose): correct application healthcheck endpoint to /health`)
- Remaining uncertainty: The `/health` endpoint only tests basic Flask process liveness. Full readiness (`/ready`), database connectivity (PostgreSQL), cache connectivity (Redis), and upstream NGINX routing still need to be verified.

---

## Entry 02 / 24/09/2026 / 9:20 AM
- Symptom: After applying the health-check fix and completing the log analysis, testing the live environment showed that the application was unable to serve traffic on the root endpoint /. 
- Hypothesis: NGINX is not correctly accepting HTTP traffic on port 8080.
- Command or test: 
```bash 
  curl -i -v http://localhost:8080/ 
```
- Actual output:
```text
> GET / HTTP/1.1
> Host: localhost:8080
> User-Agent: curl/8.5.0
> Accept: */*
> 
* Recv failure: Connection reset by peer
* Closing connection
curl: (56) Recv failure: Connection reset by peer
```
- Failed attempt and what changed your thinking: The connection to localhost:8080 was established, but the server reset the connection before returning an HTTP response. I checked the NGINX logs but found no corresponding request or error. I then inspected the container port mapping and found that Docker was forwarding host port 8080 to container port 81. I checked the NGINX configuration and confirmed that NGINX was listening on port 80, not 81. This revealed a mismatch between the Docker port mapping and the port on which NGINX was actually listening. 
- Root cause: A port mismatch between the Docker Compose configuration and the NGINX configuration: Docker forwarded traffic from host port 8080 to container port 81, while NGINX was listening on port 80.
- Fix: Corrected the Docker Compose port mapping to forward traffic from host port 8080 to container port 80 instead of 81.
- Retest evidence: After applying the fix, the connection reached NGINX successfully, which returned HTTP/1.1 502 Bad Gateway with Server: nginx/1.28.3. This confirms that the port-mapping issue was resolved, but the application still has an upstream/backend issue that requires further investigation.
  ```bash
  curl -i http://localhost:8080/
  ```
  Output:
  ```text
  HTTP/1.1 502 Bad Gateway
  Server: nginx/1.28.3
  Date: Thu, 24 Sep 2026 05:43:51 GMT
  Content-Type: text/html
  Content-Length: 157
  Connection: keep-alive

  <html>
  <head><title>502 Bad Gateway</title></head>
  <body>
  <center><h1>502 Bad Gateway</h1></center>
  <hr><center>nginx/1.28.3</center>
  </body>
  </html>
  ```
- Related commit: `0b5ef2b` (fix(compose): correct public NGINX port mapping from 8080>81 to 8080>80)  
- Remaining uncertainty: The remaining 502 Bad Gateway indicates that NGINX cannot successfully communicate with the upstream application/backend. The exact upstream cause has not yet been established and requires further investigation.

---
## Entry 03 / 24/09/2026 / 9:52 AM

- Symptom: After fixing the Docker-to-NGINX port mapping, the application root endpoint / returned HTTP 502 Bad Gateway from NGINX.
- Hypothesis: NGINX is unable to successfully communicate with the upstream application/backend.
- Command or test: 
```bash 
curl -i http://localhost:8080/
``` 
- Actual output:
 ```text
  HTTP/1.1 502 Bad Gateway
  Server: nginx/1.28.3
  Date: Thu, 24 Sep 2026 05:43:51 GMT
  Content-Type: text/html
  Content-Length: 157
  Connection: keep-alive

  <html>
  <head><title>502 Bad Gateway</title></head>
  <body>
  <center><h1>502 Bad Gateway</h1></center>
  <hr><center>nginx/1.28.3</center>
  </body>
  </html>
  ```
- Failed attempt and what changed your thinking: Initially, one application was being forwarded to port 81, while the other application used port 8080. I suspected that the different upstream port might be causing the 502 error, so I changed the NGINX upstream configuration to use port 8080 to verify whether both applications had the same issue.

After the change, the 502 response still occurred. The NGINX logs showed Connection refused when connecting to 10.0.5.3:8080. I then tested the upstream directly with curl, which also returned Connection refused.

I then checked the application logs and found that the health check was working correctly, but the application was listening on 127.0.0.1:8080. This changed my thinking from an NGINX port configuration problem to a connectivity/binding problem. The application was running, but it was only listening on the container's loopback interface, so it was not accepting connections through its Docker network IP.
- Root cause: The application was bound to 127.0.0.1:8080 instead of 0.0.0.0:8080. Therefore, NGINX could reach the application's container IP (10.0.5.3) but the application was not listening on that network interface, resulting in Connection refused and consequently 502 Bad Gateway.
- Fix: Updated the `APP_HOST` environment variable from `"127.0.0.1"` to `"0.0.0.0"` in `docker-compose.yml`, and corrected the upstream port from `app-01:8081` to `app-01:8080` in `nginx/nginx.conf`.
- Retest evidence:
```bash
curl -i http://localhost:8080/
```
Output: 
```text
HTTP/1.1 200 OK
Server: nginx/1.28.3
Date: Thu, 24 Sep 2026 13:34:18 GMT
Content-Type: application/json
Content-Length: 100
Connection: keep-alive
X-Instance-ID: app-01
X-Request-ID: 48c8ca47f978b60cdfa7acae2fd994ed
Cache-Control: no-store

{"instance_id":"app-01","message":"Welcome to BARQ Systems","service":"barq-api","version":"2.0.0"}
```
- Related commit: 
- Remaining uncertainty: The fix was verified through app-01, but app-02 has not yet been independently verified. Additionally, only the root endpoint (/) has been tested; dependency-backed endpoints (/ready, /records, /counter) still require verification.

---
## Entry / date / time
- Symptom:
- Hypothesis:
- Command or test:
- Actual output:
- Failed attempt and what changed your thinking:
- Root cause:
- Fix:
- Retest evidence:
- Related commit:
- Remaining uncertainty:

Do not fabricate a failed attempt just to fill the template. Record actual attempts.
