from flask import Flask, request, jsonify
from parser import JitterbitProjectParser
import tempfile
import os
import json

app = Flask(__name__)

# Allow large uploads (100MB+)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200MB

@app.route("/")
def home():
    return {"status": "Jitterbit Parser API Running"}

@app.route("/parse", methods=["POST"])
def parse_file():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]

    if not file.filename.endswith(".json"):
        return jsonify({"error": "Only .json project files supported"}), 400

    with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp:
        file.save(tmp.name)
        temp_path = tmp.name

    try:
        with open(temp_path, "r", encoding="utf-8") as f:
            project_json = json.load(f)

        parser = JitterbitProjectParser(project_json)
        result = parser.parse()

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        os.remove(temp_path)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)
