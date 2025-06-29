from flask import Flask, request, render_template
import asyncio
import io
import os
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"
from contextlib import redirect_stdout
from transcript_worker import process_url

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def index():
    transcript = ""
    logs = ""

    if request.method == "POST":
        url = request.form.get("video_url")

        async def run_and_capture():
            f = io.StringIO()
            with redirect_stdout(f):
                try:
                    result = await process_url(url)  # Now returns transcript directly
                except Exception as e:
                    result = "[An error occurred.]"
                    f.write(f"[ERROR] {e}\n")
            return result, f.getvalue()

        transcript, logs = asyncio.run(run_and_capture())

    return render_template("index.html", transcript=transcript, logs=logs)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
