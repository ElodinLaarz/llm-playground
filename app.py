from dotenv import load_dotenv
from flask import Flask, request, jsonify
import json
import os
import google.generativeai as genai

load_dotenv()

# --- Gemini Setup ---
try:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY environment variable not set!")
        
    genai.configure(api_key=GEMINI_API_KEY)
    
    # Create the model instance
    model = genai.GenerativeModel('gemini-2.0-flash') 
    print("✨ Gemini AI Model Initialized Successfully! ✨")

except Exception as e:
    print(f"🚨 Error initializing Gemini: {e}")
    model = None

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def github_webhook():
    """ Listens for incoming GitHub webhooks and processes them. """
    print("\n--- Webhook Received! ---")

    if not request.is_json:
        print("Request did not contain JSON data.")
        return jsonify({'error': 'Request must be JSON'}), 400

    payload = request.json
    event_type = request.headers.get('X-GitHub-Event')
    print(f"Event Type: {event_type}")

    # --- Process 'issues' events ---
    if event_type == 'issues':
        action = payload.get('action')
        print(f"Issue Action: {action}")

        # Check if it's a new issue and Gemini is ready
        if action == 'opened' and model:
            issue_data = payload.get('issue', {})
            issue_title = issue_data.get('title')
            issue_body = issue_data.get('body')
            issue_url = issue_data.get('html_url')

            print(f"Processing New Issue: {issue_title}")
            print(f"URL: {issue_url}")

            if issue_title and issue_body:
                # Craft a prompt for Gemini
                prompt = f"""
                Analyze the following GitHub issue and provide:
                1. A brief summary (1-2 sentences).
                2. Three relevant GitHub labels (e.g., 'bug', 'feature-request', 'documentation', 'question', 'enhancement').

                Issue Title: {issue_title}
                Issue Body:
                ---
                {issue_body}
                ---
                """

                try:
                    print("Sending prompt to Gemini...")
                    response = model.generate_content(prompt)
                    
                    print("\n--- Gemini Response ---")
                    print(response.text)
                    print("-------------------------\n")

                except Exception as e:
                    print(f"🚨 Error calling Gemini API: {e}")
            else:
                print("Issue title or body missing, cannot process.")
        
        elif not model:
            print("Gemini model not initialized, skipping processing.")

    # Always send back a success response to GitHub/Smee
    return jsonify({'status': 'success'}), 200

@app.route('/', methods=['GET'])
def index():
    return "<h1>Gemini Webhook Listener is Running!</h1>"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=False)
