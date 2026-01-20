import cmd
import json
import os
from typing import Dict, List, Any
import shlex
import sys
import time
from datetime import datetime, timezone

from io import StringIO
import uuid
from concurrent.futures import ThreadPoolExecutor
executor = ThreadPoolExecutor(max_workers=5)
RUNNING_FUTURES = {}
current_dir = os.path.dirname(os.path.abspath(__file__))
libs_root_path = os.path.abspath(os.path.join(current_dir, '..', '..'))
target_package_dir = os.path.join(libs_root_path, 'py-string-helpers')
sys.path.insert(0, target_package_dir)
target_package_dir = os.path.join(libs_root_path, 'py_cli')
sys.path.insert(0, target_package_dir)

import base64
import subprocess
import py_string_helpers.string_helpers as string_helpers
from py_cli.db_setup import DBManager

ALIAS_FILE = 'aliases.json'

dbManager = DBManager()

class TaskInterface:
    STATUS_PENDING = "PENDING"
    STATUS_RUNNING = "RUNNING"
    STATUS_PAUSED = "PAUSED"
    STATUS_ERROR = "ERROR"
    STATUS_COMPLETED = "COMPLETED"

    def __init__(self):
        pass

    def start_job(self, line):
        task_id = str(uuid.uuid4())
        conn = dbManager.get_db_connection()
        now_utc = datetime.now(timezone.utc)

        utc_iso_string = now_utc.strftime('%Y-%m-%dT%H:%M:%SZ')

        # Convert to ISO 8601 format
        iso_string_utc = now_utc.isoformat()
        # Set status to PENDING initially
        response = conn.execute("INSERT INTO tasks (inserted_at, id, command, status) VALUES (?, ?, ?, ?)",
                     (iso_string_utc, task_id, line, 'PENDING'))
        conn.commit()
        conn.close()
        return task_id

    def end_job(self, task_id):
        self.set_status(task_id, TaskInterface.STATUS_COMPLETED)

    def error_job(self, task_id, error_msg=""):
        self.set_status(task_id, TaskInterface.STATUS_ERROR)

    def set_msg(self, task_id, msg):
        conn = DBManager.get_db_connection()
        conn.execute("UPDATE tasks SET output = ? WHERE id = ?", (msg, task_id))
        conn.commit()
        conn.close()


    def set_output(self, task_id, output):
        conn = DBManager.get_db_connection()
        conn.execute("UPDATE tasks SET output = ? WHERE id = ?", (output, task_id))
        conn.commit()
        conn.close()

    def update_output(self, task_id, output):
        conn = DBManager.get_db_connection()
        conn.execute("""UPDATE tasks
                        SET output = output || CHAR (10) || ?, output_length = LENGTH (output || CHAR (10) || ?)
                        WHERE id = ?""", (output, output, task_id))
        conn.commit()
        conn.close()

    def set_status(self, task_id, status):
        conn = DBManager.get_db_connection()
        conn.execute("""
                     UPDATE tasks
                     SET status = ?
                     WHERE id = ?""", (status, task_id))
        conn.commit()
        conn.close()

    def clear_all_jobs(self):
        conn = DBManager.get_db_connection()
        conn.execute("""DELETE FROM tasks""")
        conn.commit()
        conn.close()

    def get_all_statuses(self, include=None):
        if include is None:
            include = ["id", "status"]
        fields = ",".join(include)

        conn = DBManager.get_db_connection()
        # Ensure row_factory is set for easy conversion to dict.
        # If DBManager.get_db_connection() doesn't set it, add it here:
        # conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # --- 1. Execute the query to get ALL rows ---
        # Removed WHERE clause to get all tasks
        cursor.execute(f"SELECT {fields}  FROM tasks")  # Added 'id' for completeness

        # 2. Get column names
        column_names = [description[0] for description in cursor.description]

        # --- 3. Fetch ALL data rows ---
        all_row_data = cursor.fetchall()
        conn.close()

        # 4. Convert all rows to a list of dictionaries
        tasks_list = []

        for row_data in all_row_data:
        # Combine names and data using zip() and convert to a dictionary
            task_dict = dict(zip(column_names, row_data))
            tasks_list.append(task_dict)

        # Return the list of dictionaries
        return tasks_list

    def get_last_task_id(self):
        """
        Retrieves the 'id' of the last task inserted into the 'tasks' table.
        Assumes 'id' is the task ID and 'inserted_at' is the column used for sorting.
        """
        conn = DBManager.get_db_connection()
        cursor = conn.cursor()

        try:
            # 1. Execute the query
            # Select the 'id' and order by 'inserted_at' descending, then limit to 1
            cursor.execute("SELECT id FROM tasks ORDER BY inserted_at DESC LIMIT 1")

            # 2. Fetch the result
            # fetchone() returns a tuple (id,) or None if no rows are found
            result = cursor.fetchone()

            # 3. Process the result
            if result:
                # Extract the ID from the tuple (the first element)
                last_id = result[0]
                return last_id
            else:
                # Table is empty
                return None

        except Exception as e:
            print(f"Database error: {e}")
            return None

        finally:
            # 4. Close the connection in the 'finally' block to ensure it always closes
            conn.close()

    """
    """
    def get_status(self, task_id, include=None, last_length=0):
        conn = DBManager.get_db_connection()
        cursor = conn.cursor()
        if include is None:
            include = ["status"]
        if "output" in include and "output_length" not in include:
            include.append("output_length")
        fields = ",".join(include)

        command = f"""SELECT {fields}
        FROM tasks WHERE id = ?"""
        # Execute the query
        cursor.execute(command, (task_id,))

        # 1. Get column names from cursor description
        # The description stores (column_name, type_code, ...)
        column_names = [description[0] for description in cursor.description]

        # 2. Fetch the data row (it will be a tuple)
        row_data = cursor.fetchone()
        conn.close()

        if not row_data:
            return ({"error": "Task not found"})
        task_dict = dict(zip(column_names, row_data))
        def create_response():
            if "output" in column_names:
                current_output = task_dict.get("output")
                total_length = task_dict.get("output_length")
                if total_length > last_length:
                    # Use Python slicing on the string: [start_index : end_index]
                    # SQLite's SUBSTR is 1-indexed, Python is 0-indexed.
                    task_dict["output"] = current_output[last_length:]
                    return (task_dict)
            else:
                return (task_dict)

        return create_response()



taskInterface = TaskInterface()
import threading

import traceback
def job_cleanup_and_error_handling(future, task_id):
    """
    Runs when the task is done (success, failure, or cancellation).
    In a real app, this is where you'd update your SQLite status.
    """
    RUNNING_FUTURES.pop(task_id, None)
    # 1. Check if an exception occurred
    exception = future.exception()

    if exception:
        try:
            future.result(timeout=0)
        except Exception:
            # 2. Capture and format the traceback as a string
            traceback_str = traceback.format_exc()

            # Now you can log the full trace to your output column or a log file
            print(f"Full Asynchronous Trace for Task: {task_id}")
            print(traceback_str)
        # --- EXCEPTION HANDLING LOGIC ---
        print(f"\n[Error Handler] Task {task_id} FAILED.")
        print(f"Error Type: {type(exception).__name__}")
        print(f"Error Message: {exception}")

        # Example: Update DB status to ERROR
        # update_task_status(task_id, "ERROR", str(exception))

    elif future.cancelled():
        # --- CANCELLATION HANDLING LOGIC ---
        print(f"\n[Cancellation Handler] Task {task_id} was cancelled.")
        # Example: Update DB status to CANCELLED
        # update_task_status(task_id, "CANCELLED", "User initiated cancellation.")

    else:
        # --- SUCCESS HANDLING LOGIC ---
        result = future.result()
        print(f"\n[Success Handler] Task {task_id} completed successfully.")
        print(f"Result was: {result}")

        # Example: Update DB status to COMPLETED
        # update_task_status(task_id, "COMPLETED", result)

    # Clean up the RUNNING_FUTURES tracking dictionary (critical step)
    # RUNNING_FUTURES.pop(task_id, None)
class Shell:
    # --- Internal State ---

    # 1. History of executed commands (handled by cmd.Cmd)
    # 2. Alias storage (loaded/saved to ALIAS_FILE)

    # 3. Last command results for referencing ($1, $2, etc.)
    last_results: None

    # --- Initialization and Setup ---

    def __init__(self, **kwargs):
        init_parms = json.loads(json.dumps(kwargs))

        def delete_kwarg(name):
            nonlocal kwargs
            if name in kwargs: del kwargs[name]

        delete_kwarg('alias_file')
        delete_kwarg('prompt')
        delete_kwarg('intro')
        delete_kwarg('run_mode')

        kwargs = init_parms
        self.shell_data = {}
        self.history_list = []
        self.alias_file = kwargs.get('alias_file', ALIAS_FILE)
        self.prompt = kwargs.get('prompt', '(shell) ')
        self.intro = kwargs.get('intro', 'Shell. Type help or ? to list commands.\n')
        self.aliases: Dict[str, List[str]] = {}
        self.load_aliases()
        self.run_mode = kwargs.get('run_mode', " console ")

    def start_long_running(self, line, cmd, arg, worker_function):
        task_id = taskInterface.start_job(line)
        arg["task_id"] = task_id
        future = executor.submit(worker_function, arg)
        future.add_done_callback(
            lambda f: job_cleanup_and_error_handling(f, task_id)
        )
        RUNNING_FUTURES[task_id] = future
        return task_id

    def preloop(self):
        """Called once before the command loop starts."""
        # Manual history setup (simple list) if readline is missing
        self.history_list = []

    def postcmd(self, response, line):
        """Executed after a command, used here to manually track history."""
        # Manually store command if readline is not available
        if line.strip() != "history" and self.is_history_recall(line) is None:
            self.history_list.append(line.strip())

    def get_previous_command(self):
        """Retrieves the last command entered by the user."""
        # Fallback for manual list
        if len(self.history_list) > 0:
            return self.history_list[-1]
        return None

    def do_prev(self, line, arg, kwargs):
        """Prints the previous command executed."""
        prev_cmd = self.get_previous_command()
        if prev_cmd:
            print(f"Previous Command: {prev_cmd}")
        else:
            print("No previous command found in history.")

    def do_history(self, line, arg, kwargs):
        """Displays the command history with line numbers."""
        output = ""
        for i, cmd_line in enumerate(self.history_list):
            # History usually starts at 1, but Python lists start at 0
            output += f'{i + 1:4}  {cmd_line}\n'
        return {"output": output}

    def is_history_recall(self, line):
        if line.startswith('!'):
            # The command to execute (initially None)
            cmd_to_exec = None

            if line == '!!':
                # !!: Execute the last command
                if self.history_list:
                    cmd_to_exec = self.history_list[-1]
                else:
                    print('*** No previous command in history.')

            elif (line.endswith(":p") and line[1:-2].isdigit()) or line[1:].isdigit():
                # !N: Execute command at line N
                if line.endswith(":p"):
                    line = line[:-2]
                try:
                    history_index = int(line[1:]) - 1  # N is 1-based, list is 0-based
                    cmd_to_exec = self.history_list[history_index]
                except IndexError:
                    print(f'*** Command not found at history index {line[1:]}.')
                except ValueError:
                    # Should not happen due to isdigit() check, but good practice
                    print('*** Invalid history recall format.')

            elif len(line) > 1:
                # !string: Execute most recent command starting with 'string'
                search_string = line[1:]
                # Iterate backwards to find the most recent match
                for cmd_line in reversed(self.history_list):
                    if cmd_line.startswith(search_string):
                        cmd_to_exec = cmd_line
                        break

                if cmd_to_exec is None:
                    print(f'*** No command found starting with "{search_string}".')

            # If a command was found, print it and execute it
            return cmd_to_exec
        return None

    def default(self, line):
        """Handles history recall (!N, !!, !string) and unknown commands."""
        # --- Shell-like History Recall ---

        cmd_to_exec = self.is_history_recall(line)
        if cmd_to_exec:
            print(f"Executing: {cmd_to_exec}")
            self.history_list.append(cmd_to_exec)
            # Use onecmd to process the retrieved command
            return self.onecmd(cmd_to_exec)
        return {"status": "bad command"}

    def load_aliases(self):
        """Loads aliases from the JSON file."""
        if os.path.exists(self.alias_file):
            try:
                with open(self.alias_file, 'r') as f:
                    self.aliases = json.load(f)
                print(f"Loaded {len(self.aliases)} aliases from {ALIAS_FILE}.")
            except json.JSONDecodeError:
                print(f"Warning: Could not decode {ALIAS_FILE}. Starting with no aliases.")
                self.aliases = {}
        else:
            self.aliases = {}

    def save_aliases(self):
        """Saves current aliases to the JSON file."""
        with open(ALIAS_FILE, 'w') as f:
            json.dump(self.aliases, f, indent=4)
        print(f"Saved {len(self.aliases)} aliases to {ALIAS_FILE}.")

    # --- Core Command Execution Override ---

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

    def run_job_in_thread(self, task_id, command_line, cli_config):
        cli_instance = self
        cli_lock = cli_config['lock']
        """Executes the CLI command in a separate thread, protected by a Lock."""
        conn = DBManager.get_db_connection()
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
        conn = DBManager.get_db_connection()  # Get a new connection for update
        cursor = conn.cursor()

        cursor.execute("UPDATE tasks SET status=?, output=?, end_time=? WHERE id=?",
                       (status, output.strip(), end_time, task_id))
        conn.commit()
        conn.close()

    def parse_input_shlex_convention(self, input_string):
        """
        Parses an input string using shlex rules, separating positional arguments
        from keyword arguments (key=value).
        """
        args = []
        kwargs = {}

        # 1. Use shlex.split() to safely tokenize the entire input string
        try:
            tokens = shlex.split(input_string)
        except ValueError as e:
            # Handles cases with unclosed quotes (e.g., 'arg "value without closing quote')
            return [], {}, f"Error in parsing quotes: {e}"

        # If the input is empty, return empty lists/dicts
        if not tokens:
            return [], {}, None

        # 2. Iterate through tokens and assign them to args or kwargs
        for token in tokens:
            # Check if the token contains an '=' sign
            if '=' in token:
                # Split only on the first '=' to allow '=' within the value
                key, value = token.split('=', 1)

                # Add to kwargs, stripping potential extra whitespace
                kwargs[key.strip()] = value.strip()
            else:
                # If no '=', treat as a positional argument
                args.append(token)

        return args, kwargs, None


    def onecmd(self, line):
        """Handles a single command line, processing aliases first."""

        # Split line into command and arguments
        try:
            if "###META" in line:
                line, meta = line.split("###META", 1)
                meta = meta.strip()
                meta = eval(meta)

            args, kwargs, error = self.parse_input_shlex_convention(line)

            if len(args) < 0:
                raise Exception(f"Invalid command line arguments: {line}")

            cmd_name = args[0]


            # 1. Alias Check and Expansion
            if cmd_name in self.aliases:
                # Expand the alias template
                template = self.aliases[cmd_name]

                # Simple argument substitution ($1, $2, etc.)
                expanded_cmd = []
                arg_index = 0

                for part in template:
                    if part.startswith('$') and part[1:].isdigit():
                        idx = int(part[1:]) - 1
                        if idx < len(args):
                            expanded_cmd.append(args[idx])
                        else:
                            print(f"Error: Alias '{cmd_name}' requires argument ${idx + 1}.")
                            return False
                    else:
                        expanded_cmd.append(part)

                # Join the expanded command back into a string and execute recursively
                full_command = ' '.join(expanded_cmd)
                print(f"Executing alias expansion: {full_command}")
                return self.onecmd(full_command)
            return self.execute_cmd(line, cmd_name, args[1:], kwargs)
        except Exception as e:
            print(f"Error: {e}")
            # 2. Standard Command Execution

    def execute_cmd(self, line, command_name, args, kwargs):
        try:
            # Check if the command exists (e.g., gets cli_instance.do_catalog)
            if not hasattr(self, 'do_' + command_name):
                raise Exception("Can't find command")
            do_func = getattr(self, 'do_' + command_name)
            return do_func(line, args, kwargs)
            # Let the command be processed by run_cli_command_sync for default/unknown command handling
            # If it's a history command (!N), run_cli_command_sync will execute it.
        except AttributeError:
            # Let the command be processed by run_cli_command_sync for default/unknown command handling
            # If it's a history command (!N), run_cli_command_sync will execute it.
            raise Exception(f"Errir Executing Command '{command_name}' not found.")
    # --- Feature 4: Result Management and Subsequent Command Use ---

    def do_help(self, line, arg, kwargs):
        return ({"output": "Available commands:"})


    def do_walk(self, line, args, kwargs):
        """ Long Running Job Example"""
        task_id = None

        def worker_function(kwargs):
            output_buffer = []
            count = 0
            if not os.path.isdir(arg):
                print(f"Error: Directory not found or is not a directory: {arg}")
                return

            taskInterface.set_status(task_id, TaskInterface.STATUS_RUNNING)
            # os.walk yields (dirpath, dirnames, filenames)
            for dirpath, dirnames, filenames in os.walk(arg):
                for filename in filenames:
                    # os.path.join safely combines the directory path and file name
                    full_path = os.path.join(dirpath, filename)
                    count += 1
                    output_buffer.append(full_path)
                    if len(output_buffer) >= 10:
                        #taskInterface.update_output(task_id,
                        #                            "\n".join(output_buffer))
                        taskInterface.set_output(task_id,
                                                    json.dumps(
                                                        {"count":count,
                                                         "last_files":output_buffer}))
                        output_buffer = []

            if output_buffer:
                taskInterface.update_output(task_id,
                                            "\n".join(output_buffer))

        if len(args) < 1:
            raise Exception("Need directory name")
        arg = args[0]
        task_id = taskInterface.start_job(line)
        future = executor.submit(worker_function, arg)
        future.add_done_callback(lambda f: RUNNING_FUTURES.pop(task_id, None))
        RUNNING_FUTURES[task_id] = future

        return {"output": {"msg": "Thread Started", "task_id": task_id
                           }}

    def do_alias(self, line, args, kwargs):
        """
        alias <name> <command>
        Defines or displays aliases. Saves aliases automatically.
        Example: alias queryraw query *.rw2 $1
        Example: alias show query
        """
        if not args or len(args) == 0:
            print("Current Aliases:")
            for name, template in self.aliases.items():
                print(f"  {name} = {' '.join(template)}")
            return

        arg = args[0]
        parts = shlex.split(arg, comments=True)
        if len(parts) < 2:
            print("Usage: alias <name> <command_template>")
            return

        name = parts[0]
        template = parts[1:]

        self.aliases[name] = template
        self.save_aliases()
        print(f"Alias '{name}' defined.")

    def do_unalias(self, line, args, kwargs):
        """unalias <name> - Removes an alias."""
        if not args or len(args) == 0:
            raise Exception("No alias specified.")
        arg = args[0]
        if arg in self.aliases:
            del self.aliases[arg]
            self.save_aliases()
            print(f"Alias '{arg}' removed.")
        else:
            print(f"Alias '{arg}' not found.")

    def do_clear_jobs(self, line, args, kwargs):
        taskInterface.clear_all_jobs()
        return {"output": "All jobs cleared."}

    """
        critirion: [{name, args, message}]
    """
    def validate_args(self, args, criteria):
        for criterion in criteria:
            if criterion['name'] == "length" and len(args) != criterion['args']:
                raise Exception(criterion['msg'])
            if criterion['name'] == "min_length" and len(args) < criterion['args']:
                raise Exception(criterion['msg'])
            if criterion['name'] == "max_length" and len(args) > criterion['args']:
                raise Exception(criterion['msg'])




    # --- Standard Commands ---
    def do_stop_task(self,line,  args, kwargs):
        self.validate_args(args, args, [
            {"name": "min_length", "args": 1, "message":"No Task ID specified"}
        ])
        task_id = args[0]
        future = RUNNING_FUTURES.get(task_id)
        if future:
            was_cancelled = future.cancel()
            if was_cancelled:
                # The callback should handle removal, but it's safe to pop here too
                RUNNING_FUTURES.pop(task_id, None)
                # ... update DB status to CANCELLED ...
                return True
        return False

    def do_get_task_status(self, line, args, kwargs):
        # required arg 0: ALL, LAST, or task_id
        # optional (kwargs) include, last_length
        include = "id, command, output, output_length, msg, status, start_time, end_time"
        task_id = None
        last_length = 0
        last_length = int(kwargs.get("last_length", "0"))
        include=kwargs.get("include", include)


        if len(args) <  1:
            raise Exception("Need a task id")
        task_id = args[0]

        include=include.split(",")
        if task_id is None or task_id == "ALL":
            status = taskInterface.get_all_statuses(include=include)
        elif task_id == "LAST":
            task_id = taskInterface.get_last_task_id()
            if task_id is None:
                raise Exception("No Task ID found")
            status = taskInterface.get_status(task_id, include=include, last_length=last_length)
        else:
            status = taskInterface.get_status(task_id, include=include, last_length=last_length)
        return {"output": status}

    def do_exit(self, line, arg, kwargs):
        """Exit the shell."""
        return {"stop": True}  # Return True to stop the command loop

    do_quit = do_exit

    def cmdloop(self):
        while True:
            user_input = input(self.prompt)
            response = self.onecmd(user_input)
            self.postcmd(response, user_input)
            if response is not None:
                if "stop" in response and response["stop"] == True: return
                print(string_helpers.pretty_print_object(response["output"]))
            else:
                print("None Response")


class WebShell(Shell):
    def __init__(self, **kwargs):
        kwargs['run_mode'] = 'server'
        super().__init__(**kwargs)


if __name__ == '__main__':
    # Initial setup for history
    print(f"History file: {os.path.join(os.getcwd(), '.history')}")
    Shell().cmdloop()
