#!/usr/bin/env python3
import asyncio
import json
import time
from collections import Counter
import websockets
import aiohttp

# API endpoint for devices
API_URL = "http://10.5.0.1/api/devices"

# Set of connected WebSocket clients
connected_clients = set()

# Global metrics and shared state
start_time = time.time()
roaming_events = 0
last_aggregated_served_by = None

packet_losses_dl = 0
packet_losses_ul = 0

packet_losses_dl_last_poll = 0
packet_losses_dl_current_poll = 0
packet_losses_ul_last_poll = 0
packet_losses_ul_current_poll = 0

# List to collect served_by values over each aggregation period
served_by_samples = []


def format_uptime(uptime_seconds):
    """Format seconds as 'Xd   Yh   Zmin' with extra spacing between groups."""
    days = int(uptime_seconds // (3600 * 24))
    hours = int((uptime_seconds % (3600 * 24)) // 3600)
    minutes = int((uptime_seconds % 3600) // 60)
    return f"{days}\u00A0d   {hours}\u00A0h   {minutes}\u00A0min"


async def broadcast(message):
    if connected_clients:
        await asyncio.gather(*(ws.send(message) for ws in connected_clients), return_exceptions=True)


def map_display_name(served_by):
    """Map raw AP IDs to display names."""
    if served_by == "AXX000004":
        return "1. Obergeschoss"
    elif served_by == "AXX000003":
        return "3. Obergeschoss"
    else:
        return served_by


async def poll_api_devices():
    global packet_losses_dl, packet_losses_ul
    global packet_losses_dl_last_poll, packet_losses_dl_current_poll
    global packet_losses_ul_last_poll, packet_losses_ul_current_poll
    global served_by_samples

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(API_URL) as response:
                    status = response.status
                    text = await response.text()
                    #print("API devices response status:", status)
                    #print("API devices response text (first 200 chars):", text[:1000])

                    try:
                        data = json.loads(text)
                    except Exception as json_err:
                        print("Failed to parse JSON:", json_err)
                        await asyncio.sleep(0.2)
                        continue

                    if isinstance(data, list):
                        client_device = next((d for d in data if d.get("role") == "client"), None)
                    else:
                        print("Unexpected JSON format; expected a list.")
                        await asyncio.sleep(0.2)
                        continue

                    if client_device and "connectionStatus" in client_device:
                        served_by = client_device["connectionStatus"].get("servedBy")
                        # Append the served_by value for aggregation
                        if served_by is not None:
                            served_by_samples.append(served_by)

                        # Update packet loss counters
                        packet_losses_dl_last_poll = packet_losses_dl_current_poll
                        packet_losses_ul_last_poll = packet_losses_ul_current_poll

                        packet_losses_dl_current_poll = (
                            client_device["connectionStatus"].get("downlinkPayloadDropCount", 0) +
                            client_device["connectionStatus"].get("downlinkLossCount", 0)
                        )
                        packet_losses_ul_current_poll = (
                            client_device["connectionStatus"].get("uplinkPayloadDropCount", 0) +
                            client_device["connectionStatus"].get("uplinkLossCount", 0)
                        )

                        packet_losses_dl_diff = packet_losses_dl_current_poll - packet_losses_dl_last_poll
                        packet_losses_ul_diff = packet_losses_ul_current_poll - packet_losses_ul_last_poll

                        packet_losses_dl += packet_losses_dl_diff
                        packet_losses_ul += packet_losses_ul_diff
                    else:
                        print("Client device not found or missing connectionStatus.")
            except Exception as e:
                print("Error polling API devices:", e)
            # Poll every 0.2 seconds
            await asyncio.sleep(0.2)


async def aggregate_and_broadcast():
    global roaming_events, last_aggregated_served_by, served_by_samples

    while True:
        # Wait for 2 seconds between broadcasts
        await asyncio.sleep(2)
        if not served_by_samples:
            print("No samples collected in this period.")
            continue

        # Determine the most frequently observed served_by value in the period
        counter = Counter(served_by_samples)
        aggregated_served_by, _ = counter.most_common(1)[0]
        served_by_display = map_display_name(aggregated_served_by)

        # Update roaming event if the aggregated served_by has changed since last broadcast
        if aggregated_served_by != last_aggregated_served_by:
            roaming_events += 1
            last_aggregated_served_by = aggregated_served_by

        uptime_seconds = time.time() - start_time
        uptime_str = format_uptime(uptime_seconds)

        message = json.dumps({
            "servedBy": served_by_display,
            "roamingCount": roaming_events,
            "uptime": uptime_str,
            "packet_losses_dl": packet_losses_dl,
            "packet_losses_ul": packet_losses_ul
        })

        print("Broadcasting aggregated message:", message)
        await broadcast(message)
        # Reset samples for the next aggregation period
        served_by_samples = []


async def ws_handler(websocket, path=None):
    connected_clients.add(websocket)
    print("New connection from", websocket.remote_address)
    try:
        async for message in websocket:
            print("Received message from client:", message)
            try:
                data = json.loads(message)
                if data.get("command") == "reset":
                    global start_time, roaming_events, packet_losses_dl, packet_losses_ul
                    start_time = time.time()      # Reset uptime
                    roaming_events = 0            # Reset roaming events
                    packet_losses_dl = 0
                    packet_losses_ul = 0
                    print("Reset command received. Metrics have been reset.")
                    continue
            except Exception as e:
                print("Error processing incoming message:", e)
    except Exception as e:
        print("Exception in connection handler:", e)
    finally:
        connected_clients.remove(websocket)
        print("Connection closed for", websocket.remote_address)


async def main():
    ws_server = websockets.serve(ws_handler, "localhost", 8080, ping_interval=20)
    await ws_server
    print("WebSocket server running on ws://localhost:8080")
    # Start both the polling and aggregation tasks concurrently
    asyncio.create_task(poll_api_devices())
    asyncio.create_task(aggregate_and_broadcast())
    await asyncio.Future()  # run forever

if __name__ == "__main__":
    asyncio.run(main())
