import asyncio
import time
import concurrent.futures

# A worker service that offloads blocking image-processing jobs, and also
# needs to answer fast health-check pings while jobs run.

def process_job(job_id):
    time.sleep(0.5)  # simulates a slow blocking call (encode, disk, etc.)
    return f"job {job_id} done"

def health_ping():
    time.sleep(0.01)  # trivially fast
    return "ok"

async def run_batch():
    loop = asyncio.get_running_loop()
    # kick off a batch of blocking jobs
    jobs = [loop.run_in_executor(None, process_job, i) for i in range(8)]
    await asyncio.sleep(0.1)

    # meanwhile a health check needs to stay responsive
    start = time.monotonic()
    await loop.run_in_executor(None, health_ping)
    ping_latency = time.monotonic() - start
    print(f"health ping latency: {ping_latency:.3f}s")

    await asyncio.gather(*jobs)

asyncio.run(run_batch())
