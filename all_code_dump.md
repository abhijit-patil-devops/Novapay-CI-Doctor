## File: analyzer/__init__.py

```python
```

---

## File: analyzer/log_parser.py

```python
import os

def extract_relevant_logs(log_file_path):
    """
    Reads a Jenkins console log file and extracts sections containing errors.
    Returns a cleaned string with context around each error.

    Args:
        log_file_path (str): Absolute path to the Jenkins log file.

    Returns:
        str: A string containing the extracted log snippets or an error message.
    """
    # Keywords that usually indicate a failure in a CI/CD pipeline
    ERROR_KEYWORDS = ["ERROR", "FAILED", "Exception", "exit code", "fatal", "Error:", "BUILD FAILURE"]
    CONTEXT_WINDOW = 15  # Lines to capture before and after the error
    MAX_CHARS = 8000      # Heuristic for ~2000 tokens to avoid hitting LLM limits

    # 1. Handle edge case: File doesn't exist
    if not os.path.exists(log_file_path):
        return "Error: Log file not found."

    # 2. Handle edge case: Very large log files (>5MB)
    # We check the size first to avoid loading gigabytes of data into memory
    file_size = os.path.getsize(log_file_path)
    if file_size > 5 * 1024 * 1024:
        # If the file is too large, we will only read the first 5MB to prevent crashes
        # In a real production environment, we might read from the end of the file (tail)
        pass

    try:
        with open(log_file_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
    except Exception as e:
        return f"Error reading log file: {str(e)}"

    # 3. Handle edge case: Empty file
    if not lines:
        return "No significant errors found in log."

    # We will store the indices of all lines that are part of an error context
    # Using a set ensures that we don't duplicate lines if two errors are close to each other
    lines_to_include = set()

    for i, line in enumerate(lines):
        # Check if any of our error keywords are in the current line
        if any(keyword in line for keyword in ERROR_KEYWORDS):
            # Mark the line itself and the window around it
            start = max(0, i - CONTEXT_WINDOW)
            end = min(len(lines), i + CONTEXT_WINDOW + 1)
            for line_num in range(start, end):
                lines_to_include.add(line_num)

    # 4. Handle case where no error keywords were found
    if not lines_to_include:
        return "No significant errors found in log."

    # 5. Merge and Deduplicate
    # Sort the indices and group them into contiguous blocks
    sorted_indices = sorted(list(lines_to_include))

    final_snippets = []
    if sorted_indices:
        start_idx = sorted_indices[0]
        end_idx = sorted_indices[0]

        for i in range(1, len(sorted_indices)):
            # If the current index is consecutive to the previous one, expand the block
            if sorted_indices[i] == end_idx + 1:
                end_idx = sorted_indices[i]
            else:
                # We've hit a gap; save the current block and start a new one
                final_snippets.append("".join(lines[start_idx : end_idx + 1]))
                start_idx = sorted_indices[i]
                end_idx = sorted_indices[i]

        # Add the last block
        final_snippets.append("".join(lines[start_idx : end_idx + 1]))

    # Join the merged blocks with a separator for clarity
    full_text = "\n\n--- Error Context Block ---\n\n".join(final_snippets)

    # 6. Token Budgeting: Trim if the log is huge
    # We keep the end of the log because the root cause is usually at the bottom
    if len(full_text) > MAX_CHARS:
        full_text = "... [Log Truncated] ...\n" + full_text[-MAX_CHARS:]

    return full_text.strip()
```

---

## File: analyzer/claude_client.py

```python
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

    # Retry logic: 3 attempts with exponential back uma for network/rate limit errors
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
```

---

## File: analyzer/notifier.py

```python
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def send_email_notification(analysis_result, pipeline_name, stage_name, build_number):
    """
    Sends a formatted HTML email notification using SMTP.

    Args:
        analysis_result (dict): The JSON result from the AI analysis.
        pipeline_name (str): Name of the pipeline.
        stage_name (str): Name of the failing stage.
        build_number (str): The Jenkins build number.

    Returns:
        bool: True if email was sent successfully, False otherwise.
    """
    # Read configuration from environment variables
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = os.getenv("SMTP_PORT", "587")
    smtp_user = os.getenv("SMTP_USERNAME")
    smtp_pass = os.getenv("SMTP_PASSWORD")
    email_from = os.getenv("EMAIL_FROM")
    email_to = os.getenv("EMAIL_TO")

    # Validate that all required credentials are provided
    if not all([smtp_host, smtp_user, smtp_pass, email_from, email_to]):
        print("❌ Error: Missing SMTP configuration in environment variables.")
        return False

    # Severity badge colors
    colors = {
        "high": "#FF4C4C",    # Bright Red
        "medium": "#FFA500",  # Orange
        "low": "#90EE90"      # Light Green
    }
    severity = analysis_result.get("severity", "medium").lower()
    badge_color = colors.get(severity, "#CCCCCC")

    # Email Subject
    severity_icon = "🔴" if severity == "high" else "🟠" if severity == "medium" else "🟢"
    subject = f"{severity_icon} [Novapay CI Doctor] Build #{build_number} Failed - {stage_name} stage"

    # HTML Body construction for a professional look
    html_content = f"""
    <html style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;">
    <body style="color: #333; background-color: #f4f7f6; padding: 20px;">
        <div style="max-width: 650px; margin: auto; background: white; border: 1px solid #ddd; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            <div style="background-color: #2c3e50; color: white; padding: 20px; text-align: center;">
                <h2 style="margin: 0;">🚀 CI Failure Analysis Report</h2>
            </div>
            <div style="padding: 20px;">
                <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                    <tr>
                        <td style="padding: 8px 0; color: #7f8c8d; width: 120px;"><strong>Pipeline:</strong></td>
                        <td style="padding: 8px 0;">{pipeline_name}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #7f8c8d;"><strong>Stage:</strong></td>
                        <td style="padding: 8px 0;">{stage_name}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #7f8c8d;"><strong>Build #:</strong></td>
                        <td style="padding: 8px 0;">#{build_number}</td>
                    </tr>
                </table>

                <div style="margin-bottom: 20px; text-align: center;">
                    <span style="background-color: {badge_color}; color: white; padding: 6px 12px; border-radius: 4px; font-weight: bold; text-transform: uppercase; font-size: 12px;">
                        {severity} Severity
                    </span>
                    <span style="margin-left: 10px; background-color: #eee; color: #666; padding: 6px 12px; border-radius: 4px; font-size: 12px;">
                        Category: {analysis_result.get("category", "N/A")}
                    </span>
                </div>

                <h3 style="color: #e74c3c; border-bottom: 2px solid #e74c3c; padding-bottom: 5px;">Root Cause</h3>
                <p style="background-color: #fff5f5; padding: 15px; border-left: 4px solid #e74c3c; color: #444;">
                    {analysis_result.get("root_cause", "No root cause identified.")}
                </p>

                <h3 style="color: #2ecc71; border-bottom: 2px solid #2ecc71; padding-bottom: 5px;">Suggested Fix</h3>
                <div style="background-color: #f0fff4; padding: 15px; border-left: 4px solid #2ecc71; color: #444; line-height: 1.6;">
                    {analysis_result.get("fix_suggestion", "No fix suggested.").replace('\\n', '<br>')}
                </div>

                <div style="margin-top: 30px; text-align: center; font-size: 11px; color: #999;">
                    AI Confidence: {analysis_result.get("confidence", "N/A")} | Generated by Novapay CI Doctor
                </div>
            </div>
        </div>
    </body>
    </html>
    """

    msg = MIMEMultipart()
    msg["From"] = email_from
    msg["To"] = email_to
    msg["Subject"] = subject
    msg.attach(MIMEText(html_content, "html"))

    # Retry logic: 2 attempts for temporary SMTP issues
    max_attempts = 2
    for attempt in range(max_attempts):
        try:
            with smtplib.SMTP(smtp_host, int(smtp_port)) as server:
                server.starttls() # Enable encryption
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
                print(f"✅ Email notification sent successfully to {email_to}")
                return True
        except Exception:
            # We just print the error to avoid crashing the main program
            print(f"⚠️ SMTP Attempt {attempt+1} failed.")
            if attempt == max_attempts - 1:
                print("❌ Failed to send email after maximum attempts.")
                return False
```

---

## File: sample_logs/docker_build_fail.log

```text
[INFO] Starting Docker build...
[INFO] Step 1/5 : FROM alpine:latest
[INFO] Step 2/5 : RUN apk add --no-cache curl
[INFO] Step 3/5 : COPY . /app
[INFO] Step 4/5 : RUN npm install
[ERROR] npm ERR! code E404
[ERROR] npm ERR! 404 Not Found: "internal-novapay-auth-lib@1.0.0"
[ERROR] npm ERR! 404 Not Found: "internal-novapay-auth-lib@1.0.0"
[ERROR] npm ERR! syscall mkdir
[ERROR] npm ERR! Path not found: /root/.npm/_cacache/ac0f1...
[FATAL] Docker build failed at step 4/5.
[ERROR] Build failed with exit code 1.
---
Jenkins Build Result: FAILURE
Stage: docker-build
Timestamp: 2026-07-01 10:00:00
```

---

## File: sample_logs/trivy_scan_fail.log

```text
[INFO] Starting Trivy security scan...
[INFO] Scanning image: novapay-app:latest
[INFO] Vulnerability report generated.
-------------------------------------------------------------------------------
ID       Severity  Package    Version    Fixed Version  Title
-------------------------------------------------------------------------------
CVE-2024-1234    CRITICAL   openssl    3.0.1      3.0.12     Remote Code Execution
CVE-202 la-5678   HIGH       libc-bin    2.31       2.35       Heap buffer overflow
-------------------------------------------------------------------------------
[ERROR] Security Gate Failed: Found 1 CRITICAL vulnerability.
[ERROR] Pipeline policy requires 0 CRITICAL vulnerabilities.
[FATAL] Trivy scan failed.
[ERROR] Build failed with exit code 2.
---
Jenkins Build Result: FAILURE
Stage: security-scan
Timestamp: 2026-07-01 10:15:00
```

---

## File: sample_logs/sonarqube_fail.log

```text
[INFO] Running SonarQube analysis...
[INFO] Sending analysis to server: http://sonar.novapay.internal
[INFO] Analysis successfully submitted.
[INFO] Waiting for Quality Gate result...
[INFO] Quality Gate Status: FAILED
-------------------------------------------------------------------------------
Condition           Actual    Required    Status
-------------------------------------------------------------------------------
Coverage on New Code 42.5%     80.0%       FAILED
Bugs on New Code     3          0          FAILED
Code Smells on New Code 12     5          FAILED
-------------------------------------------------------------------------------
[ERROR] Quality Gate failed. Build is rejected.
[ERROR] Code coverage 42.5% is below the threshold of 80%.
[FATAL] SonarQube quality gate failed.
[ERROR] Build failed with exit code 10.
---
Jenkins Build Result: FAILURE
Stage: code-quality
Timestamp: 2026-07-01 10:30:00
```
