#!/usr/bin/env python3
import asyncio
import json
import time
import websockets
import aiohttp

# API endpoint for devices
API_URL = "http://10.5.0.1/api/devices"

# Set of connected WebSocket clients
connected_clients = set()

# Metrics: record the start time and initialize roaming count and last servedBy value
start_time = time.time()
roaming_events = 0
last_served_by = None
packet_losses_dl = 0
packet_losses_ul = 0

packet_losses_dl_last_poll = 0
packet_losses_dl_current_poll = 0
packet_losses_ul_last_poll = 0
packet_losses_ul_current_poll = 0

numPolls = 0

def format_uptime(uptime_seconds):
    """Format seconds as 'Xd   Yh   Zmin' with extra spacing between groups."""
    days = int(uptime_seconds // (3600 * 24))
    hours = int((uptime_seconds % (3600 * 24)) // 3600)
    minutes = int((uptime_seconds % 3600) // 60)
    # Use a non-breaking space (\u00A0) to attach the number and unit,
    # and add three spaces between the groups.
    return f"{days}\u00A0d   {hours}\u00A0h   {minutes}\u00A0min"

async def broadcast(message):
    if connected_clients:
        await asyncio.gather(*(ws.send(message) for ws in connected_clients), return_exceptions=True)

async def poll_api_devices():
    global roaming_events, last_served_by, packet_losses_dl_last_poll, packet_losses_dl_current_poll, packet_losses_ul_last_poll, packet_losses_ul_current_poll, packet_losses_dl, packet_losses_ul
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(API_URL) as response:
                    status = response.status
                    text = await response.text()
                    print("API devices response status:", status)
                    print("API devices response text (first 200 chars):", text[:200])
                    
                    try:
                        data = json.loads(text)
                    except Exception as json_err:
                        print("Failed to parse JSON:", json_err)
                        await asyncio.sleep(1)
                        continue
                    
                    if isinstance(data, list):
                        client_device = next((d for d in data if d.get("role") == "client"), None)
                    else:
                        print("Unexpected JSON format; expected a list.")
                        await asyncio.sleep(1)
                        continue
                    
                    if client_device and "connectionStatus" in client_device:
                        served_by = client_device["connectionStatus"].get("servedBy")

                        packet_losses_dl_last_poll = packet_losses_dl_current_poll
                        packet_losses_ul_last_poll = packet_losses_ul_current_poll

                        packet_losses_dl_current_poll = client_device["connectionStatus"].get("downlinkPayloadDropCount") + client_device["connectionStatus"].get("downlinkLossCount")
                        packet_losses_ul_current_poll = client_device["connectionStatus"].get("uplinkPayloadDropCount") + client_device["connectionStatus"].get("uplinkLossCount")

                        packet_losses_dl_difference = packet_losses_dl_current_poll-packet_losses_dl_last_poll
                        packet_losses_ul_difference = packet_losses_ul_current_poll-packet_losses_ul_last_poll 

                        packet_losses_dl += packet_losses_dl_difference
                        packet_losses_ul += packet_losses_ul_difference

                        # Increment roaming count if the servedBy value changes
                        if served_by != last_served_by:
                            roaming_events += 1
                            last_served_by = served_by
                        uptime_seconds = time.time() - start_time
                        uptime_str = format_uptime(uptime_seconds)
                        
                        # Map raw AP IDs to display names
                        if served_by == "AXX000004":
                            display_name = "1. Obergeschoss"
                        elif served_by == "AXX000003":
                            display_name = "3. Obergeschoss"
                        else:
                            display_name = served_by
                        
                        message = json.dumps({
                            "servedBy": display_name,
                            "roamingCount": roaming_events,
                            "uptime": uptime_str,
                            "packet_losses_dl": packet_losses_dl,
                            "packet_losses_ul": packet_losses_ul
                        })

                        print("Broadcasting:", message)
                        await broadcast(message)
                    else:
                        print("Client device not found or missing connectionStatus.")
            except Exception as e:
                print("Error polling API devices:", e)
            await asyncio.sleep(4)

async def ws_handler(websocket, path=None):
    connected_clients.add(websocket)
    print("New connection from", websocket.remote_address)
    try:
        async for message in websocket:
            print("Received message from client:", message)
            # Try to decode the message as JSON
            try:
                data = json.loads(message)
                # Check if it's a reset command
                if data.get("command") == "reset":
                    global start_time, roaming_events, packet_losses_dl, packet_losses_ul
                    start_time = time.time()      # Reset uptime
                    roaming_events = 0            # Reset roaming events
                    packet_losses_dl = 0
                    packet_losses_ul = 0
                    print("Reset command received. Metrics have been reset.")

                    continue  # Skip further processing of this reset message.
            except Exception as e:
                print("Error processing incoming message:", e)
            # (Other message types could be processed here if needed)
    except Exception as e:
        print("Exception in connection handler:", e)
    finally:
        connected_clients.remove(websocket)
        print("Connection closed for", websocket.remote_address)

async def main():
    ws_server = websockets.serve(ws_handler, "localhost", 8080, ping_interval=20)
    await ws_server
    print("WebSocket server running on ws://localhost:8080")
    asyncio.create_task(poll_api_devices())
    await asyncio.Future()  # run forever

if __name__ == "__main__":
    asyncio.run(main())
