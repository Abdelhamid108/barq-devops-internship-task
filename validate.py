#!/usr/bin/env python3
"""Candidate deliverable: implement environment validation."""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request


def endpoint_check(url, path):
    full_url = url + path
    try:
        req = urllib.request.Request(full_url)
        with urllib.request.urlopen(req, timeout=5) as response:
            return True , f"Status code is {response.status} and endpoint {path} is reachable"
    except urllib.error.HTTPError as e:
        return False , f"Status code is {e.code} and endpoint {path} is not reachable"
    except Exception as e:
        return False , f"Error message: {e}"


def readiness_check(container_name):
    try:
        result = subprocess.run(
            [
                "docker",
                "inspect",
                "--format={{.State.Health.Status}}",
                container_name
            ],
            capture_output=True,
            text=True,
            check=True
        )

    except Exception as e:
        return False , f"Error message: {e}"

    status = result.stdout.strip()

    if status == "healthy":
        return True , f"container: {container_name} is healthy"
    elif status == "unhealthy":
        return False , f"container: {container_name} is unhealthy"
    elif status == "starting":
        return False , f"container: {container_name} is starting"
    else:
        return False , f"container: {container_name} is unknown status"


def check_exposed_ports(container_name):
    try:
        result = subprocess.run(
            [
                "docker",
                "inspect",
                "--format={{.HostConfig.PortBindings}}",
                container_name
            ],
            capture_output=True,
            text=True,
            check=True
        )

        output = result.stdout.strip()

        if not output or output in ("null", "map[]", "{}"):
            return True , f"container: {container_name} has no host port"
        return False , f"container: {container_name} has host port {output}"

    except Exception as e:
        return False , f"container: {container_name} error message: {e}"


def check_networks(container_name, expected_networks):
    try:
        result = subprocess.run(
            [
                "docker",
                "inspect",
                "--format={{range $name, $network := .NetworkSettings.Networks}}{{$name}} {{end}}",
                container_name
            ],
            capture_output=True,
            text=True,
            check=True
        )

        actual = {name.split("_")[-1] for name in result.stdout.strip().split()}
        expected = set(expected_networks)

        if actual == expected:
            return True , f"container: {container_name} has correct networks"
        return False , f"container: {container_name} has expected {expected} and got {actual}"

    except Exception as e:
        return False , f"container: {container_name} error message: {e}"

def check_backend_response(url, number_of_requests=10):
    seen = set()
    full_url = url + "/instance"
    try:
        for _ in range(number_of_requests):
            req = urllib.request.Request(full_url)
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    instance_id = data.get("instance_id")
                    seen.add(instance_id)
                else:
                    return False , f"status code {response.status}"

        if seen == {"app-01", "app-02"}:
            return True , f"both backends responded {seen}"
        else:
            return False , f"expected both backends, but saw {seen}"

    except urllib.error.HTTPError as e:
        return False , f"status code {e.code}"
    except Exception as e:
        return False , f"error message {e}"


def main():
    base_url = "http://127.0.0.1:8080"
    results = []

    print("\nChecking Public Endpoints........\n")
    endpoints = ["/", "/health", "/ready", "/instance"]
    for path in endpoints:
        results.append(endpoint_check(base_url, path))

    print("\nChecking Backend Load Balancing........\n")
    results.append(check_backend_response(base_url, number_of_requests=10))


    print("\nChecking Container Health.........\n")
    containers = ["postgres", "redis", "app-01", "app-02", "nginx"]
    for c in containers:
        results.append(readiness_check(c))

    print("\nChecking Prohibited Host Ports.........\n")
    for c in ["postgres", "redis", "app-01", "app-02"]:
        results.append(check_exposed_ports(c))

    print("\nChecking Network Isolation........\n")
    network_map = {
        "nginx": ["frontend"],
        "postgres": ["backend"],
        "redis": ["backend"],
        "app-01": ["frontend", "backend"],
        "app-02": ["frontend", "backend"],
    }
    for c, expected in network_map.items():
        results.append(check_networks(c, expected))

    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"\nValidation Summary: {passed}/{total} checks passed")
    print("==========================================")

    if all(results):
        print("OVERALL: ALL CHECKS PASSED")
        sys.exit(0)
    else:
        print("OVERALL: VALIDATION FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
 

