import argparse
import os
import json
from datetime import datetime
from dotenv import load_dotenv

from analyzer.log_parser import extract_relevant_logs
from analyzer.claude_client import analyze_failure
from analyzer.notifier import send_email_notification

def main():
    # 1. Setup CLI arguments
    parser = argparse.ArgumentParser(description="Novapay CI Doctor: AI-powered CI/CD failure analyzer")
    parser.add_argument("--log-file", required=True, help="Path to the Jenkins console log file")
    parser.add_argument("--pipeline", required=True, help="Name of the Jenkins pipeline")
    parser.add_argument("--stage", required=True, help="Name of the failing stage")
    parser.add_argument("--build", required=True, help="Jenkins build number")

    args = parser.parse_args()

    # Load environment variables
    load_dotenv()

    print(f"🚀 Starting Novapay CI Doctor Analysis...")
    print(f"Pipeline: {args.pipeline} | Stage: {args.stage} | Build: #{args.build}")

    # 2. Log Parsing Phase
    print("🔍 Parsing logs for error patterns...")
    log_snippet = extract_relevant_logs(args.log_file)

    if "Error:" in log_snippet or "No significant errors" in log_snippet:
        print("⚠️  No failure patterns found or log is empty. Exiting.")
        return

    # 3. AI Analysis Phase
    print("🤖 Calling Claude AI for root cause analysis...")
    analysis = analyze_failure(log_snippet, args.pipeline, args.stage)

    if "error" in analysis:
        print(f"❌ AI Analysis failed: {analysis['error']}")
        return

    # 4. Reporting Phase (Save to JSON)
    reports_dir = "reports"
    if not os.path.exists(reports_dir):
        os.makedirs(reports_dir)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_filename = f"report_{timestamp}_{args.build}.json"
    report_path = os.path.join(reports_dir, report_filename)

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(analysis, f, indent=4)

    print(f"💾 Full analysis report saved to: {report_path}")

    # 5. Notification Phase
    print("📧 Sending email notification...")
    email_success = send_email_notification(analysis, args.pipeline, args.stage, args.build)

    if email_success:
        print("✅ Notification sent successfully!")
    else:
        print("❌ Failed to send notification.")

    # 6. Final Summary to stdout
    print("\n" + "="*50)
    print("FINAL ANALYSIS SUMMARY")
    print("="*50)
    print(f"Root Cause: {analysis.get('root_cause')}")
    print(f"Severity:   {analysis.get('severity').upper()}")
    print(f"Category:   {analysis.get('category')}")
    print(f"Fix:        {analysis.get('fix_suggestion')}")
    print("="*50 + "\n")

if __name__ == "__main__":
    main()
