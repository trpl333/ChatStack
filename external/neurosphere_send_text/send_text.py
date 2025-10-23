from flask import Flask, request, jsonify
from twilio.rest import Client
import os
import json
import base64
from datetime import datetime

app = Flask(__name__)

# 🔐 Twilio credentials (from environment variables)
twilio_sid = os.getenv("TWILIO_ACCOUNT_SID")
twilio_token = os.getenv("TWILIO_AUTH_TOKEN")
twilio_client = Client(twilio_sid, twilio_token)

# Twilio sending number
twilio_from = "+18633433339"  # Your Twilio number

# Master directory for all calls
CALLS_DIR = "/opt/ChatStack/static/calls"
CALLS_INDEX = os.path.join(CALLS_DIR, "calls.json")


@app.route("/call-summary", methods=["POST"])
def call_summary():
    try:
        raw_data = request.get_data(as_text=True)
        print("📥 Raw body:", raw_data)
        data = json.loads(raw_data)
        print("📥 Parsed JSON:", data)

        # 🔎 Debug logging for audio
        print("📥 Top-level keys in payload:", list(data.keys()))
        if "audio_data" in data:
            print("📥 audio_data length:", len(data["audio_data"]))

        # Save entire payload to a debug file for inspection
        debug_path = os.path.join(CALLS_DIR, "last_payload.json")
        with open(debug_path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"🪵 Saved raw payload to {debug_path}")

        # Extract call SID and caller
        call_sid = (
            data.get("data", {})
                .get("metadata", {})
                .get("phone_call", {})
                .get("call_sid", "unknown")
        )
        caller = (
            data.get("data", {})
                .get("metadata", {})
                .get("phone_call", {})
                .get("external_number", "Unknown Caller")
        )

        # --- Handle transcript if present ---
        summary = (
            data.get("data", {})
                .get("analysis", {})
                .get("transcript_summary", "")
        )

        if summary:
            transcript_path = os.path.join(CALLS_DIR, f"{call_sid}.txt")
            with open(transcript_path, "w") as f:
                f.write(summary)
            print(f"📝 Transcript saved: {transcript_path}")

            # Update calls.json
            record = {
                "call_sid": call_sid,
                "date": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "caller": caller,
                "summary": summary,
                "transcript_file": f"{call_sid}.txt",
                "audio_file": f"{call_sid}.mp3"
            }

            calls_data = []
            if os.path.exists(CALLS_INDEX):
                with open(CALLS_INDEX, "r") as f:
                    try:
                        calls_data = json.load(f)
                    except json.JSONDecodeError:
                        calls_data = []

            calls_data.append(record)
            with open(CALLS_INDEX, "w") as f:
                json.dump(calls_data, f, indent=2)
            print(f"📒 Updated call index: {CALLS_INDEX}")

            # Send SMS
            transcript_url = f"https://voice.theinsurancedoctors.com/calls/{call_sid}.txt"
            audio_url = f"https://voice.theinsurancedoctors.com/calls/{call_sid}.mp3"
            message_body = (
                f"📞 Call from {caller}\n"
                f"📝 Summary: {summary[:200] + '...' if len(summary) > 200 else summary}\n\n"
                f"🔗 Transcript: {transcript_url}\n"
                f"🎧 Audio: {audio_url}"
            )

            recipients = ["+19493342332", "+19495565379"]
            for number in recipients:
                msg = twilio_client.messages.create(
                    from_=twilio_from,
                    to=number,
                    body=message_body
                )
                print(f"✅ SMS sent to {number}: {msg.sid}")

        # --- Handle audio chunk if present ---
        audio_chunk = data.get("audio_data")
        if audio_chunk:
            audio_bytes = base64.b64decode(audio_chunk)
            audio_path = os.path.join(CALLS_DIR, f"{call_sid}.mp3")
            with open(audio_path, "ab") as f:   # append mode
                f.write(audio_bytes)
            print(f"🎧 Appended audio chunk to {audio_path}")

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        print("❌ Error:", str(e))
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)
