#!/usr/bin/env python3
"""
prometheus_poller.py
Polls Prometheus every few seconds to check data and storage usage.
"""
# -------------------------------
# Import required libraries
# -------------------------------
import os
import time
import requests
import sys

# -------------------------------
# 1️⃣ Load configuration from environment variables
# -------------------------------
# PROM_URL → URL where Prometheus server is running
# INTERVAL → How often (in seconds) to fetch new data
PROM_URL = os.getenv("PROM_URL", "http://localhost:9090")  # Prometheus server
INTERVAL = int(os.getenv("INTERVAL", "5"))  # seconds

# -------------------------------
# 2️⃣ Define Prometheus metric names to query
# -------------------------------
# These metrics exist in Windows node exporter.
METRICS = {
    "disk_total_bytes": "windows_logical_disk_size_bytes",             # Total disk size
    "disk_free_bytes": "windows_logical_disk_free_bytes",              # Free space on disk
    "network_rx_bytes_total": "windows_network_bytes_received_total",  # Total data received
    "network_tx_bytes_total": "windows_network_bytes_sent_total",      # Total data sent
}

# -------------------------------
# 3️⃣ Define alert thresholds
# -------------------------------
DISK_USAGE_THRESHOLD_PCT = float(os.getenv("DISK_THRESHOLD_PCT", "80.0"))        # Alert if disk > 80%
NET_DELTA_THRESHOLD_BYTES = int(os.getenv("NET_DELTA_THRESHOLD_BYTES", str(100 * 1024 * 1024)))  # 100 MB

# -------------------------------
# 4️⃣ Prometheus API endpoint
# -------------------------------
QUERY_ENDPOINT = f"{PROM_URL.rstrip('/')}/api/v1/query"

# -------------------------------
# 5️⃣ Helper function to query Prometheus
# -------------------------------
def query_prometheus(query: str) -> dict:
    resp = requests.get(QUERY_ENDPOINT, params={"query": query}, timeout=5)
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") != "success":
        raise RuntimeError("Prometheus query failed: " + str(data))
    return data["data"]

# -------------------------------
# 6️⃣ Get the numeric value for a Prometheus metric
# -------------------------------
def instant_value_for_metric(metric_name: str) -> float:
    q = f"sum({metric_name})"
    d = query_prometheus(q)
    if not d.get("result"):
        return 0.0
    return float(d["result"][0]["value"][1])

# -------------------------------
# 7️⃣ Utility to format bytes into readable size (KB, MB, GB)
# -------------------------------
def format_bytes(b: float) -> str:
    for unit in ("B","KB","MB","GB","TB"):
        if abs(b) < 1024.0:
            return f"{b:6.2f}{unit}"
        b /= 1024.0
    return f"{b:.2f}PB"

# -------------------------------
# 8️⃣ Main polling loop
# -------------------------------
def main():
    print("Starting Prometheus poller... PROM_URL =", PROM_URL, "INTERVAL =", INTERVAL)
    last_rx = last_tx = None

    while True:
        try:
            # --- Disk usage calculation ---
            total = instant_value_for_metric(METRICS["disk_total_bytes"])
            free = instant_value_for_metric(METRICS["disk_free_bytes"])
            used = total - free
            used_pct = (used / total * 100.0) if total else 0.0

            # --- Network data ---
            rx = instant_value_for_metric(METRICS["network_rx_bytes_total"])
            tx = instant_value_for_metric(METRICS["network_tx_bytes_total"])

            # --- Delta since last measurement ---
            rx_delta = rx - last_rx if last_rx is not None else 0
            tx_delta = tx - last_tx if last_tx is not None else 0

            # --- Print current usage ---
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            print(f"\n[{ts}] Disk used: {format_bytes(used)} / {format_bytes(total)} ({used_pct:.1f}%)")
            print(f"[{ts}] Network delta (last {INTERVAL}s): RX {format_bytes(rx_delta)} TX {format_bytes(tx_delta)}")

            # --- Check for alerts ---
            if used_pct >= DISK_USAGE_THRESHOLD_PCT:
                print(f"⚠ ALERT: Disk usage exceeded threshold ({used_pct:.1f}% ≥ {DISK_USAGE_THRESHOLD_PCT}%)")
            if abs(rx_delta) >= NET_DELTA_THRESHOLD_BYTES or abs(tx_delta) >= NET_DELTA_THRESHOLD_BYTES:
                print(f"⚠ ALERT: High network usage detected!")

            # Save current readings for next iteration
            last_rx, last_tx = rx, tx

        except Exception as e:
            print("❌ ERROR while polling Prometheus:", e, file=sys.stderr)

        # Wait for the configured interval
        time.sleep(INTERVAL)

# -------------------------------
# 9️⃣ Run script
# -------------------------------
if __name__ == "__main__":
    main()
