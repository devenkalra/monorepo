# server.py
from flask import Flask, request, jsonify
from job_runner import  get_db_connection  # Import the new runner functions
from db_setup import init_db, recover_stale_jobs  # Ensure these run on startup
from job_runner import submit_job, run_cli_command_sync
from decorators import async_command
# Initialize DB and recover any jobs that crashed during the last run
init_db()
recover_stale_jobs()
from shell import Shell, WebShell
app = Flask(__name__)
from threading import Lock
cli_instance = WebShell(run_mode="server")  # The single, shared CLI state instance
cli_lock = Lock()  # The lock to protect the shared cli_instance
cli_config = {"instance":cli_instance, "lock":cli_lock}

# NOTE: The cli_instance is now managed inside job_runner.py

@app.route('/shell', methods=['POST'])
def submit_command():
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
        result = run_cli_command_sync(command_line, cli_config)

        return jsonify({
            "message": "Command executed synchronously.",
            "mode": "sync",
            "output": result['output']
        }), result['status']

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