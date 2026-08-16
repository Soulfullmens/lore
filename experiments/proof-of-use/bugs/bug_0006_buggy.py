import asyncio
import time
import concurrent.futures

# A worker service that offloads blocking image-processing jobs while also
# answering fast health-check pings. It runs a batch of jobs and one ping,
# returning the ping's response time.

def process_job(job_id):
    time.sleep(0.5)
    return f"job {job_id} done"

def health_ping():
    time.sleep(0.01)
    return "ok"

async def run_batch():
    loop = asyncio.get_running_loop()
    jobs = [loop.run_in_executor(None, process_job, i) for i in range(40)]
    await asyncio.sleep(0.1)
    start = time.monotonic()
    await loop.run_in_executor(None, health_ping)
    ping_latency = time.monotonic() - start
    await asyncio.gather(*jobs)
    return ping_latency
