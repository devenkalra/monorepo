import unittest
import unittest.mock as mock
import sqlite3
import os
import sys
import json
import uuid
import time
from io import StringIO
current_dir = os.path.dirname(os.path.abspath(__file__))
libs_root_path = os.path.abspath(os.path.join(current_dir, '..', '..'))
target_package_dir = os.path.join(libs_root_path, 'py_cli')
sys.path.insert(0, target_package_dir)
from py_cli.shell import TaskInterface, Shell, ALIAS_FILE, RUNNING_FUTURES, executor  # Replace py_cli
import py_cli

# --- Database Setup and Mocking ---

def mock_get_db_connection():
    """Returns an in-memory SQLite connection with the necessary schema."""
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row  # Crucial for dict conversion tests
    cursor = conn.cursor()
    cursor.execute("""
                   CREATE TABLE tasks
                   (
                       id            TEXT PRIMARY KEY,
                       command       TEXT,
                       status        TEXT,
                       output        TEXT,
                       output_length INTEGER DEFAULT 0,
                       start_time    REAL,
                       end_time      REAL,
                       kill_flag     INTEGER DEFAULT 0
                   )
                   """)
    conn.commit()
    return conn


# Patch the external DB connection function globally for all DB-related tests
@mock.patch('py_cli.get_db_connection', side_effect=mock_get_db_connection)
class TestTaskInterface(unittest.TestCase):

    def setUp(self):
        # Clear RUNNING_FUTURES before each test to ensure isolation
        RUNNING_FUTURES.clear()
        self.ti = TaskInterface()
        # Ensure database is clean
        self.ti.clear_all_jobs()
        self.test_command = "test command"
        self.test_id = self.ti.start_job(self.test_command)

    # --- Basic Lifecycle Tests ---

    def test_start_job(self, mock_db_conn):
        new_id = self.ti.start_job("new task")
        status = self.ti.get_status(new_id)
        self.assertIsNotNone(new_id)
        self.assertEqual(status['status'], TaskInterface.STATUS_PENDING)

    def test_end_job_and_set_status(self, mock_db_conn):
        self.ti.end_job(self.test_id)
        status = self.ti.get_status(self.test_id)
        self.assertEqual(status['status'], TaskInterface.STATUS_COMPLETED)

    def test_error_job(self, mock_db_conn):
        self.ti.error_job(self.test_id, "disk fail")
        status = self.ti.get_status(self.test_id)
        self.assertEqual(status['status'], TaskInterface.STATUS_ERROR)

    # --- Output Update Tests ---

    def test_set_output_and_set_msg(self, mock_db_conn):
        test_msg = "Initial message"
        self.ti.set_msg(self.test_id, test_msg)
        status = self.ti.get_status(self.test_id, include=["output"])
        self.assertEqual(status['output'], test_msg)

        # Test set_output (should overwrite)
        test_output = "New output"
        self.ti.set_output(self.test_id, test_output)
        status = self.ti.get_status(self.test_id, include=["output"])
        self.assertEqual(status['output'], test_output)

    def test_update_output_incremental(self, mock_db_conn):
        self.ti.set_output(self.test_id, "Line 1")
        self.ti.update_output(self.test_id, "Line 2")
        self.ti.update_output(self.test_id, "Line 3")

        # Check total output
        status = self.ti.get_status(self.test_id, include=["output", "output_length"])
        expected_output = "Line 1\nLine 2\nLine 3"
        self.assertEqual(status['output'], expected_output)
        self.assertEqual(status['length'], len(expected_output))

    # --- Status Retrieval Tests ---

    def test_get_status_incremental_slice(self, mock_db_conn):
        # 1. Populate initial data
        self.ti.set_output(self.test_id, "AA\nBB\nCC\nDD")

        # 2. Get first chunk (length is 0)
        status1 = self.ti.get_status(self.test_id, include=["output", "status"], last_length=0)
        self.assertEqual(status1['output'], "AA\nBB\nCC\nDD")

        # 3. Get second chunk (simulate client having seen "AA\n")
        # Length of "AA\n" is 3.
        last_length = 3
        status2 = self.ti.get_status(self.test_id, include=["output"], last_length=last_length)
        self.assertEqual(status2['output'], "BB\nCC\nDD")  # New output starts at index 3

    def test_get_all_statuses(self, mock_db_conn):
        self.ti.start_job("job 2")
        self.ti.start_job("job 3")

        all_tasks = self.ti.get_all_statuses(include=["id", "status"])
        self.assertEqual(len(all_tasks), 3)
        self.assertTrue(all_tasks[0]['id'] in self.test_id or all_tasks[1]['id'] in self.test_id)
        self.assertEqual(all_tasks[0]['status'], TaskInterface.STATUS_PENDING)

    def test_clear_all_jobs(self, mock_db_conn):
        self.ti.start_job("job 2")
        self.ti.clear_all_jobs()
        all_tasks = self.ti.get_all_statuses()
        self.assertEqual(len(all_tasks), 0)


# --- Shell Alias and History Tests ---

@mock.patch('os.path.exists')
@mock.patch('builtins.open', new_callable=mock.mock_open,
            read_data='{"ls": ["do_list", "."], "echo": ["do_echo", "$1"]}')
@mock.patch('py_cli.TaskInterface')  # Mock TI to prevent DB calls in Shell tests where possible
class TestShellCore(unittest.TestCase):

    def setUp(self):
        # Remove alias file after each run
        if os.path.exists(ALIAS_FILE):
            os.remove(ALIAS_FILE)

        self.shell = Shell()
        self.shell.do_list = mock.MagicMock(return_value={"output": "list_output"})
        self.shell.do_echo = mock.MagicMock(return_value={"output": "echo_output"})
        self.shell.default = mock.MagicMock(wraps=self.shell.default)

    def tearDown(self):
        if os.path.exists(ALIAS_FILE):
            os.remove(ALIAS_FILE)

    # --- Initialization and I/O Tests ---

    def test_alias_loading_success(self, mock_ti, mock_open, mock_exists):
        mock_exists.return_value = True
        self.shell = Shell()  # Reloads aliases
        self.assertIn('ls', self.shell.aliases)
        self.assertIn('echo', self.shell.aliases)

    def test_alias_saving(self, mock_ti, mock_open, mock_exists):
        self.shell.aliases = {"test": ["test_cmd", "arg"]}
        self.shell.save_aliases()
        handle = mock_open()
        # Verify that json.dump was called correctly
        handle.write.assert_called_once()

    # --- Alias Command Tests ---

    def test_do_alias_define_and_save(self, mock_ti, mock_open, mock_exists):
        # Define a new alias
        self.shell.do_alias(['show', 'do_help'])
        self.assertIn('show', self.shell.aliases)
        self.assertEqual(self.shell.aliases['show'], ['do_help'])
        # Check if save_aliases was called
        mock_open.assert_called_with(ALIAS_FILE, 'w')

    def test_do_unalias(self, mock_ti, mock_open, mock_exists):
        self.shell.aliases = {"temp": ["cmd"], "keep": ["cmd2"]}
        self.shell.do_unalias(['temp'])
        self.assertNotIn('temp', self.shell.aliases)
        self.assertIn('keep', self.shell.aliases)

    # --- Alias Expansion Tests (onecmd) ---

    def test_onecmd_alias_expansion(self, mock_ti, mock_open, mock_exists):
        # Setup alias: alias echo do_echo $1
        self.shell.aliases = {"echo": ["do_echo", "$1"]}

        # Execution path: onecmd("echo hello world") -> execute_cmd("do_echo", ["hello world"], {})
        self.shell.execute_cmd = mock.MagicMock()

        # Since the tokenization inside onecmd is complex, we mock the result of parse_input
        with mock.patch.object(self.shell, 'parse_input_shlex_convention',
                               return_value=(['echo', 'hello', 'world'], {}, None)):
            self.shell.onecmd("echo hello world")

            # The execution logic should be called with the expanded command
            self.shell.execute_cmd.assert_called_once_with('do_echo', ['hello'], {})

    def test_onecmd_alias_expansion_multiple_args(self, mock_ti, mock_open, mock_exists):
        # Setup alias: alias swap do_swap $2 $1
        self.shell.aliases = {"swap": ["do_swap", "$2", "$1"]}
        self.shell.execute_cmd = mock.MagicMock()

        with mock.patch.object(self.shell, 'parse_input_shlex_convention',
                               return_value=(['swap', 'first', 'second'], {}, None)):
            self.shell.onecmd("swap first second")

            # The execution logic should be called with 'second' and 'first' swapped
            self.shell.execute_cmd.assert_called_once_with('do_swap', ['second', 'first'], {})

    # --- History Tests ---

    def test_postcmd_history_tracking(self, mock_ti, mock_open, mock_exists):
        self.shell.history_list = []
        self.shell.postcmd(None, "command 1")
        self.shell.postcmd(None, "command 2  ")
        self.assertEqual(self.shell.history_list, ["command 1", "command 2"])

    def test_do_history(self, mock_ti, mock_open, mock_exists):
        self.shell.history_list = ["cmd1", "cmd2"]
        result = self.shell.do_history(None)
        expected_output = '   1  cmd1\n   2  cmd2\n'
        self.assertEqual(result["output"], expected_output)

    def test_history_recall_last_cmd(self, mock_ti, mock_open, mock_exists):
        self.shell.history_list = ["cmd1", "cmd2"]
        self.shell.onecmd = mock.MagicMock(return_value={"status": "executed"})

        # Test !! recall
        result = self.shell.default("!!")
        self.shell.onecmd.assert_called_with("cmd2")
        self.assertEqual(self.shell.history_list[-1], "cmd2")  # History list should append the executed command

    def test_history_recall_by_index(self, mock_ti, mock_open, mock_exists):
        self.shell.history_list = ["cmd1", "cmd2", "cmd3"]
        self.shell.onecmd = mock.MagicMock(return_value={"status": "executed"})

        # Test !1 recall (1-based index)
        self.shell.default("!1")
        self.shell.onecmd.assert_called_with("cmd1")

    def test_history_recall_by_prefix(self, mock_ti, mock_open, mock_exists):
        self.shell.history_list = ["ls -l", "grep foo", "ls -a"]
        self.shell.onecmd = mock.MagicMock(return_value={"status": "executed"})

        # Test !ls (should recall most recent starting with 'ls', which is 'ls -a')
        self.shell.default("!ls")
        self.shell.onecmd.assert_called_with("ls -a")


# --- Shell Argument Parsing Tests ---

class TestShellArgumentParsing(unittest.TestCase):

    def setUp(self):
        self.shell = Shell()

    def test_parse_input_shlex_basic(self):
        line = "command arg1 arg2"
        args, kwargs, error = self.shell.parse_input_shlex_convention(line)
        self.assertEqual(args, ["command", "arg1", "arg2"])
        self.assertEqual(kwargs, {})
        self.assertIsNone(error)

    def test_parse_input_shlex_quotes(self):
        line = 'command "argument with spaces" arg2'
        args, kwargs, error = self.shell.parse_input_shlex_convention(line)
        self.assertEqual(args, ["command", "argument with spaces", "arg2"])
        self.assertEqual(kwargs, {})
        self.assertIsNone(error)

    def test_parse_input_shlex_kwargs(self):
        line = 'command arg1 key1=value1 key2="value with spaces"'
        args, kwargs, error = self.shell.parse_input_shlex_convention(line)
        self.assertEqual(args, ["command", "arg1"])
        self.assertEqual(kwargs, {"key1": "value1", "key2": "value with spaces"})
        self.assertIsNone(error)

    def test_parse_input_shlex_mixed(self):
        line = 'run path/to/file.txt type=raw log="detailed output"'
        args, kwargs, error = self.shell.parse_input_shlex_convention(line)
        self.assertEqual(args, ["run", "path/to/file.txt"])
        self.assertEqual(kwargs, {"type": "raw", "log": "detailed output"})
        self.assertIsNone(error)

    def test_parse_input_shlex_error(self):
        line = 'command "unclosed quote'
        args, kwargs, error = self.shell.parse_input_shlex_convention(line)
        self.assertIsNotNone(error)
        self.assertEqual(args, [])
        self.assertEqual(kwargs, {})


# --- Shell Asynchronous Job Tests ---

@mock.patch('py_cli.db_setup.get_db_connection', side_effect=mock_get_db_connection)
@mock.patch('os.path.isdir', return_value=True)
@mock.patch('os.walk')
class TestShellAsync(unittest.TestCase):

    def setUp(self):
        RUNNING_FUTURES.clear()
        self.shell = Shell()
        self.test_dir = '/mock/path'

    def test_do_walk_submits_job(self, mock_os_walk, mock_isdir, mock_db_conn):
        # Mock os.walk to return a few items immediately
        mock_os_walk.return_value = [
            (self.test_dir, ['subdir'], ['file1.txt']),
        ]

        # Mock the worker function to finish quickly
        # We need to test the submission logic, not the full execution loop

        # Use a real executor and worker function, but isolate the execution

        # Call the command (this is sync and returns immediately)
        result = self.shell.do_walk([self.test_dir], {})

        # Assert initial return structure
        self.assertIn("output", result)
        self.assertIn("task_id", result["output"])

        task_id = result["output"]["task_id"]

        # Assert job is tracked by Future
        self.assertIn(task_id, RUNNING_FUTURES)
        future = RUNNING_FUTURES[task_id]

        # Assert job is running (or will run)
        self.assertFalse(future.done())

        # Wait for the job to complete (forces the thread pool to execute)
        future.result()

        # Assert job is removed from RUNNING_FUTURES by callback
        self.assertNotIn(task_id, RUNNING_FUTURES)

        # Assert final status in DB (requires waiting for future)
        ti = py_cli.shell.TaskInterface()
        status = ti.get_status(task_id, include=["status"])
        self.assertEqual(status['status'], TaskInterface.STATUS_COMPLETED)  # Assuming worker finished without error