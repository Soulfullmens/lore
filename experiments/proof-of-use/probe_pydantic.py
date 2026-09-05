from gemini_agent import call_agent

prompt = """This Pydantic v2 code should uppercase the name field, but when I create User() with no arguments, name stays lowercase "guest" instead of "GUEST". Fix it.

from pydantic import BaseModel, field_validator

class User(BaseModel):
    name: str = "guest"

    @field_validator("name")
    @classmethod
    def upper(cls, v):
        return v.upper()

print(User().name)  # want "GUEST", get "guest"
"""

print("--- SENDING PROMPT TO GEMINI-3.1-FLASH-LITE ---")
response = call_agent(prompt)
print("--- RESPONSE FROM MODEL ---")
print(response)
