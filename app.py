from datetime import datetime, timedelta
from dotenv import load_dotenv
from flask import Flask, request, jsonify
import google.generativeai as genai
import json
import jwt
import os
import requests
import time

load_dotenv()

try:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GITHUB_APP_ID = os.getenv("GITHUB_APP_ID")
    GITHUB_PRIVATE_KEY_PATH = os.getenv("GITHUB_PRIVATE_KEY_PATH")

    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not set!")
    if not GITHUB_APP_ID:
        raise ValueError("GITHUB_APP_ID not set!")
    if not GITHUB_PRIVATE_KEY_PATH:
        raise ValueError("GITHUB_PRIVATE_KEY_PATH not set!")

    with open(GITHUB_PRIVATE_KEY_PATH, "r") as key_file:
        GITHUB_PRIVATE_KEY = key_file.read()

    print("Environment variables and Private Key loaded.")

except Exception as e:
    print(f"🚨 Error loading configuration: {e}")
    GEMINI_API_KEY = GITHUB_APP_ID = GITHUB_PRIVATE_KEY = None


model = None
if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.0-flash")
        print("✨ Gemini AI Model Initialized Successfully! ✨")
    except Exception as e:
        print(f"🚨 Error initializing Gemini: {e}")


def create_jwt(app_id, private_key):
    """Creates a JSON Web Token (JWT) for GitHub App authentication."""
    now = int(time.time())
    payload = {
        "iat": now - 60,  # Issued at time (60 seconds in the past)
        "exp": now + (9 * 60),  # Expiration time (10 minutes max)
        "iss": app_id,  # Issuer (your App ID)
    }
    encoded_jwt = jwt.encode(payload, private_key, algorithm="RS256")
    print("🔑 JWT Created.")
    return encoded_jwt


def get_installation_token(app_id, private_key, installation_id):
    """Gets an installation access token for a specific installation."""
    jwt_token = create_jwt(app_id, private_key)
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Accept": "application/vnd.github.v3+json",
    }
    token_url = (
        f"https://api.github.com/app/installations/{installation_id}/access_tokens"
    )

    try:
        response = requests.post(token_url, headers=headers)
        response.raise_for_status()
        token_data = response.json()
        print(f"🔒 Installation Token Obtained (expires: {token_data['expires_at']}).")
        return token_data["token"]
    except requests.exceptions.RequestException as e:
        print(f"🚨 Error getting installation token: {e}")
        print(f"Response content: {response.content}")
        return None


def add_comment_to_issue(issue_url, token, comment_body):
    """Adds a comment to a GitHub issue."""
    comments_url = f"{issue_url}/comments"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    data = {"body": comment_body}

    try:
        response = requests.post(comments_url, headers=headers, json=data)
        response.raise_for_status()
        print(f"💬 Comment added successfully to {issue_url}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"🚨 Error adding comment: {e}")
        print(f"Response content: {response.content}")
        return False


app = Flask(__name__)


@app.route("/webhook", methods=["POST"])
def github_webhook():
    """Listens for incoming GitHub webhooks and processes them."""
    print("\n--- Webhook Received! ---")
    if not (GITHUB_APP_ID and GITHUB_PRIVATE_KEY and model):
        print("🚨 App not fully configured. Skipping processing.")
        return jsonify({"status": "config_error"}), 500

    if not request.is_json:
        print("Request did not contain JSON data.")
        return jsonify({"error": "Request must be JSON"}), 400

    payload = request.json
    event_type = request.headers.get("X-GitHub-Event")
    print(f"Event Type: {event_type}")

    installation_id = payload.get("installation", {}).get("id")
    if not installation_id:
        print("🚨 No installation ID found in payload. Cannot authenticate.")
        return jsonify({"error": "missing_installation_id"}), 400

    if event_type == "issues" and payload.get("action") == "opened":
        issue_data = payload.get("issue", {})
        issue_title = issue_data.get("title")
        issue_body = issue_data.get("body")
        issue_url = issue_data.get("html_url")
        issue_api_url = issue_data.get("url")

        print(f"Processing New Issue: {issue_title} ({issue_url})")

        if issue_title and issue_body:
            prompt = f"Analyze this GitHub issue and provide a brief summary (1-2 sentences). Issue Title: {issue_title}\nIssue Body:\n---\n{issue_body}\n---"

            try:
                print("Sending prompt to Gemini...")
                response = model.generate_content(prompt)
                gemini_summary = response.text.strip()
                print(
                    f"--- Gemini Summary ---\n{gemini_summary}\n----------------------"
                )

                # --- NOW ACT ON GITHUB ---
                print("Attempting to authenticate with GitHub...")
                access_token = get_installation_token(
                    GITHUB_APP_ID, GITHUB_PRIVATE_KEY, installation_id
                )

                if access_token:
                    print("Authentication successful. Adding comment...")
                    comment = f"🤖 **Gemini Analysis:**\n\n{gemini_summary}"
                    add_comment_to_issue(issue_api_url, access_token, comment)
                else:
                    print("🚨 Could not get access token. Cannot add comment.")

            except Exception as e:
                print(f"🚨 Error during Gemini processing or GitHub action: {e}")
        else:
            print("Issue title or body missing.")

    return jsonify({"status": "success"}), 200


@app.route("/", methods=["GET"])
def index():
    return "<h1>Gemini GitHub Bot is Running!</h1>"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000, debug=False)
