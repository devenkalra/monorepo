# server.py
from flask import Flask, request, jsonify
import sys
import os

from werkzeug.utils import send_from_directory

current_dir = os.path.dirname(os.path.abspath(__file__))
libs_root_path = os.path.abspath(os.path.join(current_dir, '..', '..', '..', "libs"))
target_package_dir = os.path.join(libs_root_path, 'py-string-helpers')
sys.path.insert(0, target_package_dir)
target_package_dir = os.path.join(libs_root_path, 'py_cli')
target_package_dir = os.path.join(libs_root_path, 'py_cli')
sys.path.insert(0, target_package_dir)
from urllib.parse import parse_qs
from py_cli.db_setup import DBManager
from py_string_helpers import string_helpers

#from py_cli.job_runner import  get_db_connection  # Import the new runner functions
from py_cli.job_runner import submit_job, run_cli_command_sync
from py_cli.decorators import async_command
# Initialize DB and recover any jobs that crashed during the last run
from flask import send_from_directory, abort
db = DBManager()

from catalog_shell import CatalogShell
app = Flask(__name__)
from threading import Lock
cli_instance = CatalogShell(run_mode="server")  # The single, shared CLI state instance
cli_lock = Lock()  # The lock to protect the shared cli_instance
cli_config = {"instance":cli_instance, "lock":cli_lock}

# NOTE: The cli_instance is now managed inside job_runner.py

volume_paths={
    "SYN_PHOTO": "/mnt/photo"
}


@app.route("/images")
def images():
    volume = request.args.get("volume")
    rel_path = request.args.get("path", "")  # optional
    filename = request.args.get("filename")

    if not volume or not filename:
        abort(400, "Missing required query params: volume and filename")

    base_dir = volume_paths.get(volume)
    if not base_dir:
        abort(404, f"Unknown volume: {volume}")

    # IMPORTANT: if rel_path starts with '/', os.path.join will ignore base_dir
    rel_path = rel_path.lstrip("/")

    directory = os.path.join(base_dir, rel_path)

    # Optional: ensure directory exists (helps debugging)
    if not os.path.isdir(directory):
        abort(404, f"Directory not found: {directory}")

    path = os.path.join(directory, filename)
    if not os.path.isfile(path):
        abort(404, f"File not found: {filename} in {directory}")
    return send_from_directory(directory, filename)

@app.route('/shell', methods=['GET'])
@app.route('/shell', methods=['POST'])
def submit_command():
    if request.method == 'GET':
        data = request.query_string.decode()
        data = parse_qs(data)
        if "command" in data:
            data["command"] = data["command"][0]
    else:
        data = request.get_json()
    command_line = data.get('command', '').strip()

    if not command_line:
        return jsonify({"error": "No command provided."}), 400

    command_word = command_line.split()[0].lower()

    # 1. Introspection: Get the actual do_ function object using the imported cli_instance
    try:
        # Check if the command exists (e.g., gets cli_instance.do_catalog)
        do_func = getattr(cli_instance, 'do_' + command_word)
    except AttributeError:
        # Let the command be processed by run_cli_command_sync for default/unknown command handling
        # If it's a history command (!N), run_cli_command_sync will execute it.
        pass

        # 2. Check the function's annotation
    # We check the function found via introspection, or assume it's sync if not found
    is_async = getattr(do_func, 'run_mode', 'sync') == 'async' if 'do_func' in locals() else False

    if is_async:
        # --- PATH A: LONG RUNNING (ASYNC) ---
        task_id = submit_job(command_line, cli_config)
        return jsonify({
            "message": "Command submitted for background processing.",
            "mode": "async",
            "task_id": task_id,
            "status_check_url": f"/status/{task_id}"
        }), 202

    else:
        # --- PATH B: SHORT RUNNING (SYNC) ---
        # The imported run_cli_command_sync handles the execution and output capture
        response = cli_instance.onecmd(command_line)
        cli_instance.postcmd(response, command_line)
        if response is not None:
            if "stop" in response and response["stop"] == True: return
            print(string_helpers.pretty_print_object(response["output"]))
        else:
            print("None Response")


        return jsonify({
            "message": "Command executed synchronously.",
            "mode": "sync",
            "output": response['output']
        })

@app.route('/status/<task_id>', methods=['GET'])
def get_task_status(task_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT status, output, start_time, end_time, command FROM tasks WHERE id=?", (task_id,))

    result = cursor.fetchone()
    conn.close()

    if result is None:
        return jsonify({"error": "Task ID not found."}), 404

    status, output, start_time, end_time, command = result

    response = {
        'state': status,
        'command': command,
        'start_time': start_time,
    }

    if status in ('SUCCESS', 'FAILED'):
        response['result'] = output
        response['end_time'] = end_time

    return jsonify(response)


if __name__ == '__main__':
    # Flask app should be run behind a WSGI server (like Gunicorn) in production,
    # but app.run() is fine for local development.
    app.run(host='0.0.0.0', port=5000)