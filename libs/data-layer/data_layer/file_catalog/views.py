from rest_framework import serializers, viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import File, Folder, Task
from concurrent.futures import ThreadPoolExecutor
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.pagination import LimitOffsetPagination
executor = ThreadPoolExecutor(max_workers=5)

from .task_interface import TaskInterface

from .exif_worker import scan_and_upload
# --- Serializers ---

class MyTaskInterface(TaskInterface):
    def __init__(self, ):
        super().__init__()

    def add_file_status(self, task_id, filepath, status, logs):
        logs = "\n".join(logs)

        self.update_file_status(task_id, filepath + " " + status)

    def update_file(self, doc, files):
        pass

    def update_folder(self, doc):
        pass


task_interface = MyTaskInterface()

class FolderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Folder
        fields = '__all__'


class FileSerializer(serializers.ModelSerializer):
    class Meta:
        model = File
        fields = '__all__'


class TaskSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Task
        fields = '__all__'
        read_only_fields = ['status', 'result', 'error_message']


# --- Views ---

class FolderViewSet(viewsets.ModelViewSet):
    queryset = Folder.objects.all()
    serializer_class = FolderSerializer


class TaskViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only endpoint to check the status of tasks.
    """
    queryset = Task.objects.all().order_by('-created_at')
    serializer_class = TaskSerializer

import shlex

def parse_input_shlex_convention(input_string):
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

import traceback
RUNNING_FUTURES = {}
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
from rest_framework.views import APIView
class CatalogIngestView(APIView):
    def post(self, request):
        # 1. Parse the JSON string from the 'data' form field
        # (Recall: requests.post sent it as a string to handle the nested structure)

        doc = request.data

        # 2. Extract specific fields from your 'doc' JSON
        # Adjust these keys to match your actual cataloger JSON structure

        # 3. Get the file (if provided)
        # request.FILES matches the 'files={'thumbnail': ...}' in your python script
        thumbnail = request.FILES.get('thumbnail')

        # ONE LINE EXECUTION
        entry, action = File.objects.ingest(doc, thumbnail_file=thumbnail)

        return Response({"id": entry.id, "action": action})

class FileViewSet(viewsets.ModelViewSet):
    queryset = File.objects.all()
    serializer_class = FileSerializer

    filter_backends = [
        DjangoFilterBackend,
        filters.OrderingFilter,
        filters.SearchFilter
    ]
    filterset_fields = {
        'name': ['exact', 'icontains', 'startswith'],  # Text searches
        'path': ['exact', 'icontains', 'startswith'],  # Text searches
        'mime': ['exact', 'icontains', 'startswith'],  # Text searches
        'size': ['exact', 'lt', 'gt', 'range'],  # Number searches
        'created_at': ['exact', 'year', 'gte'],  # Date searches
        'volume': ['exact']  # ID/Relationship searches
    }

    ordering_fields = ['created_at',  'size', 'name', 'path', 'volume', 'mime']
    ordering = ['-created_at']
    pagination_class = LimitOffsetPagination

    def start_long_running(self, line, cmd, arg, task_interface, worker_function):
        task = Task.objects.create(
            command=line,
            parameters=arg,
            status=Task.Status.PENDING
        )
        arg["task_id"] = task.id
        future = executor.submit(worker_function, arg, task_interface)
        future.add_done_callback(
            lambda f: job_cleanup_and_error_handling(f, task.id)
        )
        RUNNING_FUTURES[task.id] = future
        return task.id

    # Custom action to handle /api/files/command=xyz
    @action(detail=False, methods=['post', 'get'], url_path='command=(?P<command>.+)')
    def execute_command(self, request, command=None):
        """
        Endpoint to trigger long-running commands.
        Creates a Task object and returns its ID for monitoring.

        Usage Examples:
        POST /api/files/command=reindex (Body: {"target": "all"})
        """

        # Access parameters
        query_params = request.query_params
        body_data = request.data

        # Merge params (Body takes precedence)
        params = {**query_params.dict(), **body_data}

        command_word = command.split()[0].lower()

        allowed_commands = ['reindex', 'clean', 'catalog']

        if command_word not in allowed_commands:
            return Response(
                {'error': f'Unknown command: {command}. Allowed: {allowed_commands}'},
                status=status.HTTP_400_BAD_REQUEST
            )


            # --- PATH B: SHORT RUNNING (SYNC) ---
            # The imported run_cli_command_sync handles the execution and output capture
        args, kwargs, error = parse_input_shlex_convention(command)
        scan_dir = args[1]
        volume_tag = args[2]
        task_id = self.start_long_running(command, command_word,
                                          {"volume_tag":volume_tag, "scan_dir":scan_dir,
                                            "kwargs":kwargs}, task_interface, scan_and_upload)



        # Create the Task Record


        # TODO: Trigger the actual background worker here
        # e.g., celery_app.send_task('tasks.process_command', args=[task.id])

        return Response({
            'message': 'Task submitted successfully',
            'task_id': task_id,
            'monitor_url': f'/api/tasks/{task_id}/'
        }, status=status.HTTP_202_ACCEPTED)