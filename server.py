"""Assignment 2: REST API starter. Replace TODO sections with your implementation.

This deliberately does not implement the assignment's core functionality.
Run: python server.py
"""

from dotenv import load_dotenv
load_dotenv() # <--- This must run before os.environ.get()


import os
import sqlite3
import uuid
import datetime
from datetime import timezone, datetime
from pathlib import Path
import requests
from flask import Flask, jsonify, request, send_from_directory

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
DB_PATH = BASE_DIR / "iot_home.db"
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}


IMAGGA_API_KEY = os.environ.get("IMAGGA_API_KEY")
IMAGGA_API_SECRET = os.environ.get("IMAGGA_API_SECRET")
USE_MOCK_TAGS = os.environ.get("USE_MOCK_TAGS", "false").lower() == "true"



app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

#database_file = "C:/Users/727/Documents/PROG23372/Python-Projects/Assignment2/image.db"
"""Databases Functions"""
def initialize_database():
    """TODO: Create images and tags tables if they do not exist."""
    create_table = """
                
                CREATE TABLE IF NOT EXISTS images (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp  TEXT    NOT NULL,
                    filename   TEXT    UNIQUE NOT NULL
                );

                
                CREATE TABLE IF NOT EXISTS tags (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    imageId    INTEGER NOT NULL,
                    tag        TEXT    NOT NULL,
                    confidence REAL    NOT NULL,
                    FOREIGN KEY (imageId) REFERENCES images(id) ON DELETE CASCADE,
                    UNIQUE(imageId, tag) -- Ensures the same normalized tag cannot appear twice for the same image
                );
            """
    try:
        with db_connect() as conn:
            cursor = conn.cursor()
            cursor.executescript(create_table)
            conn.commit()
            print("Database initialized successfully.")
    except sqlite3.OperationalError as e:
         print("Failed to initialize database:", e)


def db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn    

"""Other Functions"""
#check file type is allowed by file extension
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_image_tags(file_path):
    if USE_MOCK_TAGS:
        return [
            {"tag": "sample", "confidence": 99.5},
            {"tag": "image", "confidence": 95.0},
            {"tag": "upload", "confidence": 88.2}
        ]
    url = "https://api.imagga.com/v2/tags"
    if not IMAGGA_API_KEY or not IMAGGA_API_SECRET:
        print("Error: IMAGGA_API_KEY and IMAGGA_API_SECRET environment variables are not set.")
        return []
    
    try:
        with open(file_path, "rb") as image_file:
            response = requests.post(
                url,
                auth=(IMAGGA_API_KEY, IMAGGA_API_SECRET),
                files={"image": image_file}
            )
            
        if response.status_code == 200:
            data = response.json()
            tags_data = []
            
            raw_tags = data.get("result", {}).get("tags", [])
            
            for item in raw_tags:
                tag_name = item.get("tag", {}).get("en")
                confidence = item.get("confidence")
                
                if tag_name and confidence is not None:
                    normalized_tag = tag_name.strip().lower()
                    tags_data.append({
                        "tag": normalized_tag,
                        "confidence": float(confidence)
                    })
                    
            return tags_data
        else:
            print(f"Imagga API error ({response.status_code}): {response.text}")
            return []
            
    except Exception as e:
        print(f"Failed to connect to Imagga API: {str(e)}")
        return []

"""API REST Functions"""
@app.post("/api/image")
def upload_image():
    # TODO: Validate multipart field named 'image', file type, file content,
    # unique filename, Imagga or mock tagging, SQLite persistence,
    # appropriate HTTP error handling, and a JSON response (201 Created).
    #check image is in files
    if 'image' not in request.files:
        return jsonify({"error": "No 'image' file field found in request"}), 400
    file = request.files['image']

    #check image was selected
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    #check if file is image type
    if not allowed_file(file.filename):
        return jsonify({"error": f"Invalid file type. Allowed types: {list(ALLOWED_EXTENSIONS)}"}), 400

    try:
        #try creating a new name for the image
        original_name = file.filename

        if original_name:
            if '.' in original_name:
                ext = original_name.rsplit('.', 1)[1].lower()
            else:
                ext = 'bin'
        else:
            original_name = "unknown_file"
            ext = 'bin'

        unique_filename = f"{uuid.uuid4().hex}.{ext}"
        file_path = os.path.join(UPLOAD_DIR, unique_filename)

        #save new file name
        file.save(file_path)


        #get the img tags from api imagga using get_image_tags() fn
        tags_data = get_image_tags(file_path)
        
        #get current time for upload
        upload_time = datetime.now().isoformat()


        #update database
        with db_connect() as conn:
            cursor = conn.cursor()
            
            #insert image record
            cursor.execute(
                """
                INSERT OR IGNORE INTO images (timestamp, filename)
                VALUES (?, ?)
                """,
                (upload_time, unique_filename)
            )
            image_id = cursor.lastrowid
            
            #img tags records
            for item in tags_data or []:
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO tags (imageId, tag, confidence)
                    VALUES (?, ?, ?)
                    """,
                    (image_id, item['tag'], item['confidence'])
                )
            
            conn.commit()

            #rturn 201 Created with JSON respo
            return jsonify({
                "image": {
                    "id": image_id,
                    "originalName": original_name,
                    "filename": unique_filename,
                    "timestamp": upload_time,
                    "tags": tags_data
                }
            }), 201
        
    except Exception as e:
        print("Error uploading image", e)
        return jsonify({"error": f"An error occurred during upload: {str(e)}"}), 500



@app.get("/api/tags")
def get_tags():
    # TODO: Parse 'from' and 'to' as ISO 8601 UTC timestamps; validate range;
    # return sorted distinct tags for images in [from, to).
    
    #parse from and to in the arguments from the url
    from_str = request.args.get('from')
    to_str = request.args.get('to')
    cleaned_from = from_str.replace('Z', '+00:00') if from_str else ''
    cleaned_to = to_str.replace('Z', '+00:00') if to_str else ''


    
    #check if both to and from are in the request, otherwise return error 400
    try:
        # Standardize 'Z' to '+00:00' for safe parsing
        cleaned_from = from_str.replace('Z', '+00:00') if from_str else ''
        cleaned_to = to_str.replace('Z', '+00:00') if to_str else ''
        
        from_dt = datetime.fromisoformat(cleaned_from)
        to_dt = datetime.fromisoformat(cleaned_to)
        
        # If one is naive and the other aware, make both naive (or both aware)
        if from_dt.tzinfo is not None and to_dt.tzinfo is None:
            to_dt = to_dt.replace(tzinfo=timezone.utc)
        elif from_dt.tzinfo is None and to_dt.tzinfo is not None:
            from_dt = from_dt.replace(tzinfo=timezone.utc)
            
    except ValueError:
        return jsonify({"error": "Invalid timestamp format. Use ISO 8601 (e.g., 2026-10-01T10:00:00Z)"}), 400

    #ensure that from is before to (from is older/smaller than to)
    if from_dt > to_dt:
        return jsonify({"error": "'from' timestamp must be less than or equal to 'to' timestamp"}), 400

    #try the connection and get the tags
    try:
        with db_connect() as conn:
            cursor = conn.cursor()
            
            # Query distinct tags for images satisfying: from <= timestamp < to
            # SQLite string comparison works seamlessly with standard ISO 8601 timestamps
            cursor.execute(
                """
                SELECT DISTINCT t.tag
                FROM tags t
                JOIN images i ON t.imageId = i.id
                WHERE i.timestamp >= ? AND i.timestamp < ?
                ORDER BY t.tag ASC
                """,
                (from_str, to_str)
            )
            
            rows = cursor.fetchall()
            
            #take tags into array to give for json
            tags = [row["tag"] for row in rows]

        #return array of tags and other data
        return jsonify({
            "from": from_str,
            "to": to_str,
            "tags": tags
        }), 200

    except Exception as e:
        return jsonify({"error": f"Failed to retrieve tags: {str(e)}"}), 500


@app.get("/api/personDetected")
def person_detected():
    # TODO: Return true if an image in [from, to) has 'person' or 'human'
    # with confidence >= 40.0. Use your stored confidence scores.
    
    #parse from and to in the arguments from the url
    from_str = request.args.get('from')
    to_str = request.args.get('to')
    cleaned_from = from_str.replace('Z', '+00:00') if from_str else ''
    cleaned_to = to_str.replace('Z', '+00:00') if to_str else ''
    
    
    #check if both to and from are in the request, otherwise return error 400
    if not from_str or not to_str:
        return jsonify({"error": "Both 'from' and 'to' query parameters are required"}), 400

    try:
        # Standardize 'Z' to '+00:00' for safe parsing
        cleaned_from = from_str.replace('Z', '+00:00') if from_str else ''
        cleaned_to = to_str.replace('Z', '+00:00') if to_str else ''
        
        from_dt = datetime.fromisoformat(cleaned_from)
        to_dt = datetime.fromisoformat(cleaned_to)
        
        # If one is naive and the other aware, make both naive (or both aware)
        if from_dt.tzinfo is not None and to_dt.tzinfo is None:
            to_dt = to_dt.replace(tzinfo=timezone.utc)
        elif from_dt.tzinfo is None and to_dt.tzinfo is not None:
            from_dt = from_dt.replace(tzinfo=timezone.utc)
            
    except ValueError:
        return jsonify({"error": "Invalid timestamp format. Use ISO 8601 (e.g., 2026-10-01T10:00:00Z)"}), 400

    #ensure that from is before to (from is older/smaller than to)
    if from_dt > to_dt:
        return jsonify({"error": "'from' timestamp must be less than or equal to 'to' timestamp"}), 400

    #try the connection and check
    try:
        with db_connect() as conn:
            cursor = conn.cursor()
            
            #check if any matching tag exists within the time range
            #Uses LOWER() to ensure case-insensitive matching for 'person' or 'human'
            cursor.execute(
                """
                SELECT 1
                FROM tags t
                JOIN images i ON t.imageId = i.id
                WHERE i.timestamp >= ? 
                  AND i.timestamp < ?
                  AND LOWER(t.tag) IN ('person', 'human', 'people', 'man', 'woman')
                  AND t.confidence >= 40.0
                LIMIT 1
                """,
                (from_str, to_str)
            )
            
            match = cursor.fetchone()
            
            #if row is found, it is true and person is detected
            is_detected = match is not None

        #return the result if the person is detected
        return jsonify({
            "from": from_str,
            "to": to_str,
            "personDetected": is_detected
        }), 200

    except Exception as e:
        return jsonify({"error": f"Failed to check person detection: {str(e)}"}), 500

@app.get("/api/popularTags")
def popular_tags():
    # TODO: Return top 5 tags by count of DISTINCT associated images,
    # descending count then alphabetical tag. Counts must be JSON numbers.
    
    try:
        with db_connect() as conn:
            cursor = conn.cursor()
            
            #select tags, gets count by distinct image id, sorts count by desc (so highest is at the top), tags by alph order
            cursor.execute(
                """
                SELECT tag, COUNT(DISTINCT imageId) AS count
                FROM tags
                GROUP BY tag
                ORDER BY count DESC, tag ASC
                LIMIT 5
                """
            )
            
            rows = cursor.fetchall()
            
            #returns results array with each tag and count, in rows.
            results = [{"tag": row["tag"], "count": row["count"]} for row in rows]
            
            return jsonify(results), 200

    except Exception as e:
        return jsonify({"error": f"Failed to retrieve popular tags: {str(e)}"}), 500




@app.get("/api/image/<filename>")
def get_image(filename):
    # TODO: Return only files from UPLOAD_DIR after safe filename handling.
    """
    Retrieve an uploaded image by its filename.
    Safely prevents path traversal attacks and handles missing files.
    """
    try:
        #send_from_directory stops attempts to get files from out of directory,
        #and returns 404 if the file is not found.
        return send_from_directory(UPLOAD_DIR, filename)
    except Exception as e:
        return jsonify({"error": "Image not found"}), 404

if __name__ == "__main__":
    initialize_database()
    host = os.getenv("SERVER_HOST", "127.0.0.1")
    port = int(os.getenv("SERVER_PORT", "5000"))
    app.run(host=host, port=port, debug=False)
