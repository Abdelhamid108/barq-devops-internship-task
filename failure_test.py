#!/usr/bin/env python3
"""Candidate deliverable: stop one backend, measure traffic, restore it and verify."""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

# function to stop the container
def stop_container(container_name):
    container_name = container_name
    try:
        subprocess.run(["docker", "stop", container_name], check=True, capture_output=True, text=True)
        return True , None # return true and none if the container is stopped successfully we return none to error parmeter because there is no error
    except Exception as e:
        return False, e.stderr.strip() if e.stderr else str(e) # return false and the docker error message if it exist or exception message if it doesn't exist

# function to start the container
def start_container(container_name):
    try:
        subprocess.run(["docker", "start", container_name], check=True,capture_output=True,text=True)
        return True , None # return true and none if the container is started successfully we return none to error parmeter because there is no error
    except Exception as e:
        return False, e.stderr.strip() if e.stderr else str(e) # return false and the docker error message if it exist or exception message if it doesn't exist

# function to measure the traffic
def measure_traffic(url,endpoint,requests_count):
    stats={
        "total_requests": requests_count,
        "success_requests": 0,
        "failed_requests": 0,
        "success_rate": 0,
    }
    for _ in range(requests_count):
        try:
            req = urllib.request.Request(url + endpoint)
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    stats["success_requests"] += 1
                else:
                    stats["failed_requests"] += 1
        except Exception:
            stats["failed_requests"] += 1
    # calculate the success rate
    if stats["total_requests"] > 0:
        stats["success_rate"] = round((stats["success_requests"] / stats["total_requests"]) * 100, 1)
    return stats
        
# function to verify the recovery
def verify_recovery(url, target_instance,max_attempts):
    for attempt in range(max_attempts):
        try:
            req = urllib.request.Request(url + "/instance")
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    current_instance = data.get("instance_id")
                    if current_instance == target_instance:
                        return True
        except Exception:
            pass # if the request fails we ignore it and try again 
        time.sleep(1)
    return False

# function to print the traffic report
def print_trrafic_report(stats):
    print("Traffic Report:")
    print(f"Total requests: {stats['total_requests']}")
    print(f"Success requests: {stats['success_requests']}")
    print(f"Failed requests: {stats['failed_requests']}")
    print(f"Success rate: {stats['success_rate']}%")


def get_base_url():
    if len(sys.argv) > 1:
        return sys.argv[1].rstrip("/")
    port = os.environ.get("PUBLIC_PORT")
    if not port and os.path.exists(".env"):
        try:
            with open(".env") as f:
                for line in f:
                    if line.startswith("PUBLIC_PORT="):
                        port = line.split("=", 1)[1].strip().strip('"\'')
                        break
        except Exception:
            pass
    return f"http://127.0.0.1:{port or '8080'}"


def main():
    base_url = get_base_url()
    target_instance = "app-01"
    
    try:
        print(f"Stopping backend: {target_instance}.....")
        success, error = stop_container(target_instance)
        if not success:
            print(f"Failed to stop backend: {target_instance} error: {error}")
            sys.exit(1)
        print(f"PASS: {target_instance} stopped successfully")

        print(f"Measuring traffic...")
        stats = measure_traffic(base_url, "/", 10)
        print_trrafic_report(stats)

    finally:
        print(f"Restoring backend: {target_instance}.....")
        success, error = start_container(target_instance)
        if not success:
            print(f"Failed to start backend: {target_instance} error: {error}")
            sys.exit(1)
        print(f"PASS: {target_instance} started successfully")
        print(f"Verifying recovery for {target_instance}.....")
        success = verify_recovery(base_url, target_instance, 15)
        if success:
            print(f"PASS: {target_instance} restored and served traffic")

            print("\nMeasuring traffic after recovery (10 requests)...")
            recovered_stats = measure_traffic(base_url, "/", 10)
            print_trrafic_report(recovered_stats)

            if recovered_stats["failed_requests"] == 0:
                print("PASS: System fully recovered to 100% availability")
                print("\nOVERALL: FAILURE & RECOVERY TEST PASSED")
                sys.exit(0)
            else:
                print(f"FAIL: Unexpected errors after recovery ({recovered_stats['failed_requests']} failed)")
                sys.exit(1)
        else:
            print(f"FAIL: {target_instance} did not serve any requests after recovery")
            print("\nOVERALL: FAILURE & RECOVERY TEST FAILED")
            sys.exit(1)


        

if __name__ == "__main__":
    main()
    