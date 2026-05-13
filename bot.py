import anthropic
from dotenv import load_dotenv
from configs import get_system_prompt

load_dotenv()
client = anthropic.Anthropic()

def get_bot_response(messages: list, business_type: str = "clinic") -> str:
    system = get_system_prompt(business_type)

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        system=system,
        messages=messages
    )
    return response.content[0].text
