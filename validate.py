#!/usr/bin/env python3
"""Candidate deliverable: implement environment validation."""

import os
import subprocess
import sys
import requests


def endpoint_check(url, path):
    try:
        response = requests.get(
            url + path,
            timeout=5
        )

        if response.status_code == 200:
            print(f"PASS {url + path} is reachable")
            return True
        else:
            print(
                f"FAIL {url + path} "
                f"status code {response.status_code}"
            )
            return False

    except Exception as e:
        print(f"FAIL {url + path} error {e}")
        return False


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
        print(f"FAIL {container_name}: {e}")
        return False

    status = result.stdout.strip()

    if status == "healthy":
        print(f"PASS {container_name} is healthy")
        return True
    elif status == "unhealthy":
        print(f"FAIL {container_name} is unhealthy")
        return False
    elif status == "starting":
        print(f"WARN {container_name} is starting")
        return False
    else:
        print(f"FAIL {container_name}: unknown status '{status}'")
        return False


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
            print(f"PASS {container_name}: no host port")
            return True

        print(f"FAIL {container_name}: host port {output}")
        return False

    except Exception as e:
        print(f"FAIL {container_name}: error {e}")
        return False


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
            print(f"PASS {container_name}: correct networks")
            return True

        print(f"FAIL {container_name}: expected {expected}, got {actual}")
        return False

    except Exception as e:
        print(f"FAIL {container_name}: error {e}")
        return False

def check_backend_response(url, number_of_requests=10):
    seen = set()
    try:
        for _ in range(number_of_requests):
            response = requests.get(
                url + "/instance",
                timeout=5
            )
            if response.status_code == 200:
                instance_id = response.json().get("instance_id")
                seen.add(instance_id)
            else:
                print(f"FAIL /instance status code {response.status_code}")
                return False

        if seen == {"app-01", "app-02"}:
            print(f"PASS both backends responded: {seen}")
            return True
        else:
            print(f"FAIL expected both backends, but saw: {seen}")
            return False

    except Exception as e:
        print(f"FAIL /instance error {e}")
        return False


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
 

