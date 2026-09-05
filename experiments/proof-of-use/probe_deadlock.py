from gemini_agent import call_agent

prompt = """The following Python program hangs and never completes. Fix it so it runs correctly.

import asyncio, sys

CHILD = '''import sys
sys.stdout.write("START\\n");sys.stdout.flush()
sys.stderr.write("E"*1000000);sys.stderr.flush()
sys.stdout.write("END\\n");sys.stdout.flush()
'''

async def run():
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-c", CHILD,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    out = await proc.stdout.read()
    err = await proc.stderr.read()
    await proc.wait()
    return out, err

asyncio.run(run())
"""

print("--- SENDING PROMPT TO GEMINI-3.1-FLASH-LITE ---")
response = call_agent(prompt)
print("--- RESPONSE FROM MODEL ---")
print(response)
