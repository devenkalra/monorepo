# job_runner.py
from concurrent.futures import ThreadPoolExecutor

from io import StringIO
import sys
import uuid
import time
import sqlite3

# Import your CLI class (Shell) and decorators

from .db_setup import DB_NAME


# --- CENTRALIZED RESOURCES ---
executor = ThreadPoolExecutor(max_workers=5)



# (You would define run_job_in_thread and submit_job here as before)

# --- NEW: Synchronous Execution Function ---
def run_cli_command_sync(command_line, cli_config):
    """
    Executes a short command synchronously and returns output immediately.
    This function uses the shared cli_instance and protects it with the cli_lock.
    """

    cli_lock = cli_config['lock']
    cli_instance = cli_config['instance']

    old_stdout = sys.stdout
    redirected_output = StringIO()
    sys.stdout = redirected_output

    output = ""
    status = 200  # HTTP status code

    try:
        # --- CRITICAL SECTION: Acquire Lock ---
        with cli_lock:
            cli = cli_instance

            # Process the full lifecycle (precmd, onecmd, postcmd)
            modified_line = cli.precmd(command_line)
            stop_flag = cli.onecmd(modified_line)
            cli.postcmd(stop_flag, command_line)
        # --- CRITICAL SECTION ENDS ---

        sys.stdout.flush()
        output = redirected_output.getvalue().strip()

    except Exception as e:
        output = f"Error during synchronous command execution: {e}"
        status = 500

    finally:
        sys.stdout = old_stdout

    return {"output": output, "status": status}

def run_job_in_thread(task_id, command_line, cli_config):
    cli_instance = cli_config['instance']
    cli_lock = cli_config['lock']
    """Executes the CLI command in a separate thread, protected by a Lock."""
    conn = get_db_connection()
    cursor = conn.cursor()

    start_time = time.time()
    # 1. Set status to RUNNING
    cursor.execute("UPDATE tasks SET status='RUNNING', start_time=? WHERE id=?",
                   (start_time, task_id))
    conn.commit()

    # Setup output capture
    old_stdout = sys.stdout
    redirected_output = StringIO()
    sys.stdout = redirected_output

    status = "SUCCESS"
    output = ""

    try:
        # --- CRITICAL SECTION: Acquire Lock ---
        with cli_lock:
            # This ensures only ONE thread can execute cli_instance methods at a time.
            cli = cli_instance
            # Process the command lifecycle
            modified_line = cli.precmd(command_line)
            cli.onecmd(modified_line)
            cli.postcmd(False, command_line)
        # --- CRITICAL SECTION ENDS: Lock Released ---

        sys.stdout.flush()
        output = redirected_output.getvalue()

    except Exception as e:
        output = f"An execution error occurred: {e}"
        status = "FAILED"

    finally:
        sys.stdout = old_stdout  # Restore stdout

    # 2. Update status to SUCCESS/FAILED and store output
    end_time = time.time()
    conn = get_db_connection()  # Get a new connection for update
    cursor = conn.cursor()

    cursor.execute("UPDATE tasks SET status=?, output=?, end_time=? WHERE id=?",
                   (status, output.strip(), end_time, task_id))
    conn.commit()
    conn.close()


def submit_job(command_line):
    """Creates a DB entry and submits the job to the ThreadPoolExecutor."""
    task_id = str(uuid.uuid4())
    conn = get_db_connection()

    # Set status to PENDING initially
    conn.execute("INSERT INTO tasks (id, command, status) VALUES (?, ?, ?)",
                 (task_id, command_line, 'PENDING'))
    conn.commit()
    conn.close()

    # Submit job to the thread pool (non-blocking)
    executor.submit(run_job_in_thread, task_id, command_line)

    return task_id