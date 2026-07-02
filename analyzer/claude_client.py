import os
import json
import time
import anthropic
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def analyze_failure(log_snippet, pipeline_name, stage_name):
    """
    Sends failure logs to Claude AI to get a root cause analysis.

    Args:
        log_snippet (str): The extracted relevant logs.
        pipeline_name (str): Name of the failing pipeline.
        stage_name (str): Name of the failing stage.

    Returns:
        dict: A JSON object with analysis or an error message.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return {"error": "ANTHROPIC_API_KEY not found in environment variables."}

    # Initialize the Anthropic client
    client = anthropic.Anthropic(api_key=api_key)

    # System prompt to guide Claude's persona and output format
    system_prompt = (
        "You are a Senior DevOps Engineer with 15 years of experience in CI/CD pipeline optimization and debugging. "
        "Your goal is to analyze raw build logs and provide a concise, technical root cause analysis. "
        "Be precise, avoid fluff, and prioritize actionable fixes. "
        "You MUST respond in strict JSON format only. Do not include any conversational text or markdown code blocks. "
        "Use the following JSON schema:\n"
        "{\n"
        "  \"root_cause\": \"short 1-2 sentence explanation\",\n"
        "  \"fix_suggestion\": \"step-by-step fix, numbered\",\n"
        "  \"severity\": \"low | medium | high\",\n"
        "  \"category\": \"docker | jenkins | security-scan | code-quality | network | dependency | other\",\n"
        "  \"confidence\": \"high | medium | low\"\n"
        "}"
    )

    user_prompt = (
        f"Pipeline: {pipeline_name}\n"
        f"Stage: {stage_name}\n"
        f"Log Snippet:\n{log_snippet}"
    )

    # Retry logic: 3 attempts with exponential backoff for network/rate limit errors
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1000,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}]
            )

            content = response.content[0].text

            # Clean up the response: Strip any markdown fences (```json ... ```)
            content = content.strip()
            if content.startswith("```"):
                # Remove the opening fence (e.g., ```json)
                content = content.split("\n", 1)[-1]
                # Remove the closing fence (```)
                if content.endswith("```"):
                    content = content.rsplit("```", 1)[0]
            content = content.strip()

            # Parse the cleaned text into a JSON dictionary
            return json.loads(content)

        except (anthropic.APIConnectionError, anthropic.RateLimitError) as e:
            if attempt == max_retries - 1:
                return {"error": f"API failure after {max_retries} attempts: {str(e)}"}
            # Exponential backoff: 2s, 4s, 8s...
            time.sleep(2 ** (attempt + 1))
        except json.JSONDecodeError:
            # If the JSON is still invalid after cleaning, return the error key
            return {"error": "Claude returned a response that could not be parsed as JSON."}
        except Exception as e:
            # Catch-all for other unexpected errors
            return {"error": f"An unexpected error occurred: {str(e)}"}
