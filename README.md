
# 🩺 Novapay CI Doctor

**Novapay CI Doctor** is an AI-powered CI/CD failure analyzer that integrates with Jenkins to automatically diagnose build failures. Instead of spending hours manually combing through massive console logs, this tool extracts only the relevant error context and uses the Claude 3.5 Sonnet model to provide a high-fidelity root cause analysis and a step-by-step fix.

## 🚩 Problem Statement
In large-scale enterprise CI/CD pipelines (like Novapay's 18-stage DevSecOps pipeline), a single failure can generate thousands of lines of logs. DevOps engineers often spend a significant amount of time simply *finding* the error before they can even begin to *fix* it. **Novapay CI Doctor** automates this discovery phase, reducing the Mean Time to Repair (MTTR).

## 🏗️ Architecture
```text
[ Jenkins Pipeline ] 
       │
       ▼
[ Console Log File ] ──────► [ Log Parser ] ──────► [ Claude 3.5 Sonnet ]
                                   │                         │
                                   │                         ▼
                                   │               [ JSON Analysis Report ]
                                   │                         │
                                   ▼                         ▼
                         [ Local Reports/ ] ◄────── [ Email Notifier ]
```

## 🛠️ Tech Stack
- **Language:** Python 3.11
- **AI Model:** Claude 3.5 Sonnet (via Anthropic SDK)
- **Deployment:** Docker (slim image)
- **Notifications:** SMTP (Standard Python Library)
- **Configuration:** python-dotenv

## 🚀 Getting Started

### 1. Setup
Clone the repository and install dependencies:
```bash
git clone <repo-url>
cd novapay-ci-doctor
pip install -r requirements.txt
```

### 2. Environment Configuration
Create a `.env` file based on `.env.example`:
```bash
cp .env.example .env
```
Fill in your `ANTHROPIC_API_KEY` and SMTP details.

> [!IMPORTANT]
> **Gmail Users:** You cannot use your normal Gmail password. You must generate an **"App Password"** from your Google Account settings (Security $\rightarrow$ 2-Step Verification $\rightarrow$ App Passwords).

### 3. Usage Example
Run the tool locally against a sample log:
```bash
python main.py --log-file sample_logs/docker_build_fail.log --pipeline "Payment-Gateway-CI" --stage "docker-build" --build "42"
```

**Sample Output:**
```text
🚀 Starting Novapay CI Doctor Analysis...
🔍 Parsing logs for error patterns...
🤖 Calling Claude AI for root cause analysis...
💾 Full analysis report saved to: reports/report_20260701_123000_42.json
📧 Sending email notification...
✅ Notification sent successfully!

==================================================
FINAL ANALYSIS SUMMARY
==================================================
Root Cause: Missing internal-novapay-auth-lib dependency in the registry.
Severity: HIGH
Category: dependency
Fix: 1. Verify the internal registry is reachable.
     2. Check if the library version 1.0.0 is published.
==================================================
```

## 🔌 Jenkins Integration
To integrate this tool into your pipeline, add the following snippet to your `Jenkinsfile` within the `post { failure { ... } }` block. Refer to `Jenkinsfile-hook-sample.groovy` for the complete implementation.

```groovy
sh "curl -s ${BUILD_URL}consoleText > build.log"
sh "docker run --rm -v ${WORKSPACE}:/app -e ANTHROPIC_API_KEY=... novapay-ci-doctor --log-file /app/build.log ..."
```

## 🔮 Future Improvements
- [ ] **Slack/Microsoft Teams Integration:** Send real-time alerts to developer channels.
- [ ] **Web Dashboard:** A historical view of all build failures and their resolutions.
- [ ] **GitHub Actions Support:** Extend the tool to support GH Actions logs.
- [ ] **Multi-Model Support:** Allow switching between Claude Opus and Sonnet based on failure complexity.

---
## 🐳 Docker Image

Pull and run directly from GitHub Container Registry:

\`\`\`bash
docker pull ghcr.io/abhijit-patil-devops/novapay-ci-doctor:latest

docker run --rm --env-file .env ghcr.io/abhijit-patil-devops/novapay-ci-doctor:latest \
  --log-file sample_logs/docker_build_fail.log \
  --pipeline "Novapay-Pipeline" \
  --stage "Build" \
  --build "42"
\`\`\`

**Note:** Requires a `.env` file with your own `ANTHROPIC_API_KEY` and SMTP credentials (see `.env.example`).
*Developed as part of the Novapay-App DevSecOps pipeline enhancement.*
=======
# Novapay-CI-Doctor
b30c9287ed4b9eb4731ff12ee74f377ef96ebb1b
