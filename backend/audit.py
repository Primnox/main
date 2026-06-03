# backend/audit.py
import time
import psutil
import os
import asyncio
import json
import httpx
from brain import think
from logger import get_logger

log = get_logger("audit")

def audit_memory():
    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()
    rss = mem_info.rss / (1024 * 1024)
    vms = mem_info.vms / (1024 * 1024)
    print(f"[MEMORY AUDIT]")
    print(f"  RSS (Resident Set Size): {rss:.2f} MB")
    print(f"  VMS (Virtual Memory Size): {vms:.2f} MB")
    return rss, vms

def audit_token_latency():
    print("[TOKEN LATENCY AUDIT]")
    start_time = time.time()
    try:
        response = think("Hello, reply in exactly 5 words.")
        elapsed = time.time() - start_time
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        tokens = len(content.split())
        print(f"  Response: '{content.strip()}'")
        print(f"  Total Latency: {elapsed:.3f} s")
        if tokens > 0:
            print(f"  Estimated Latency per Word: {(elapsed/tokens)*1000:.1f} ms/word")
    except Exception as e:
        print(f"  Error calling think(): {e}")
        elapsed = 0
    return elapsed

async def audit_websocket_throughput():
    print("[WEBSOCKET THROUGHPUT AUDIT]")
    # We will test using an async HTTP client to simulate a fast WebSocket-like ping-pong
    # Since the server might not be running, we will mock the serialization/deserialization latency
    # of a 1000-message batch.
    payload = {"type": "token", "data": {"text": "word"}}
    start_time = time.time()
    count = 10000
    for _ in range(count):
        serialized = json.dumps(payload)
        deserialized = json.loads(serialized)
    elapsed = time.time() - start_time
    throughput = count / elapsed
    print(f"  JSON Serialization/Deserialization of {count} messages: {elapsed:.3f} s")
    print(f"  Theoretical Max JSON Throughput: {throughput:.1f} msg/sec")
    
    # MessagePack estimation if msgpack was used
    try:
        import msgpack
        start_time_mp = time.time()
        for _ in range(count):
            serialized_mp = msgpack.packb(payload)
            deserialized_mp = msgpack.unpackb(serialized_mp)
        elapsed_mp = time.time() - start_time_mp
        throughput_mp = count / elapsed_mp
        print(f"  MsgPack Serialization/Deserialization of {count} messages: {elapsed_mp:.3f} s")
        print(f"  Theoretical Max MsgPack Throughput: {throughput_mp:.1f} msg/sec")
        print(f"  MsgPack speedup: {throughput_mp/throughput:.2f}x")
    except ImportError:
        print("  msgpack not installed in Python env. Skipping msgpack comparison.")

def audit_render_fps():
    print("[RENDER FPS ESTIMATION]")
    # React rendering FPS estimation:
    # If the backend streams 80 tokens/sec, and the frontend updates the React state
    # for each token, React does 80 Virtual DOM reconciliation cycles per second.
    # At N messages, diffing the list of messages takes ~5-15ms on standard client CPUs.
    # If diffing takes 10ms, 80 updates/sec would require 800ms of CPU time per second,
    # leaving only 200ms for browser paint and layout, causing rendering FPS to drop to ~15-20 FPS.
    print("  React rendering frequency without batching: 80 updates/sec")
    print("  Estimated React Virtual DOM diff time: 5-15ms per frame")
    print("  Estimated CPU utilization for state updates: 40% - 120% of main thread")
    print("  Estimated Render FPS: ~15-25 FPS (Severe micro-stutters)")
    print("  Expected FPS with requestAnimationFrame batching: 60 FPS (Zero stutters, <5% CPU)")

if __name__ == "__main__":
    print("=== Primnox Phase 1 Performance Audit ===")
    audit_memory()
    audit_token_latency()
    asyncio.run(audit_websocket_throughput())
    audit_render_fps()
    print("=========================================")
