import os
import sys
from datetime import datetime, timezone
import json
#from exif_worker import scan_and_upload
from exif_worker import scan_and_upload
from libs.py_cli.py_cli.db_setup import DBManager

current_dir = os.path.dirname(os.path.abspath(__file__))
libs_root_path = os.path.abspath(os.path.join(current_dir, '..', '..', '..', "libs"))
target_package_dir = os.path.join(libs_root_path, 'py-string-helpers')
sys.path.insert(0, target_package_dir)
target_package_dir = os.path.join(libs_root_path, 'py_cli')
sys.path.insert(0, target_package_dir)

from py_cli.shell import Shell, TaskInterface
dbManager = DBManager()


class MyTaskInterface(TaskInterface):
    def __init__(self, ):
        super().__init__()

    def add_file_status(self, task_id, filepath, status, logs):
        logs = "\n".join(logs)
        conn = dbManager.get_db_connection()
        conn = dbManager.get_db_connection()
        now_utc = datetime.now(timezone.utc)

        utc_iso_string = now_utc.strftime('%Y-%m-%dT%H:%M:%SZ')

        # Convert to ISO 8601 format
        iso_string_utc = now_utc.isoformat()
        # Set status to PENDING initially
        response = conn.execute("INSERT INTO catalog_files (inserted_at, task_id, file_path, status, extended) VALUES (?, ?, ?, ?, ?)",
                                (iso_string_utc, task_id, filepath, status, logs))
        conn.commit()
        conn.close()


taskInterface = MyTaskInterface()


class CatalogShell(Shell):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        conn = dbManager.get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS catalog_files
                    (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        inserted_at TEXT NOT NULL,
                        task_id TEXT NOT NULL,
                        file_path TEXT NOT NULL,
                        status TEXT NOT NULL,
                        extended TEXT DEFAULT '',                    
                        FOREIGN KEY (task_id)
                            REFERENCES tasks(id)
                            ON DELETE CASCADE
                            ON UPDATE CASCADE
                                        )
                       ''')
        conn.commit()
        conn.close()


    def do_recatalog(self):
        return{"output":{"msg":"Not Implemented"}}

    def do_catalog_stats(selfself, line, args, kwargs):
        task_id = None
        if len(args) < 1:
            raise Exception("Need task_id")
        task_id = args[0]
        return {"output":{"msg":"Not Implemented"}}

    def do_catalog(self, line, args, kwargs):
        """
        catalog a folder
        catalog scan_dir volume_tag start_dir= skip_on=name,size,hash
        """
        task_id = None
        if len(args) < 2:
            print(self.do_catalog.__doc__)
            raise Exception("Need scandirs and volume_tags")
        scan_dir = args[0]
        volume_tag = args[1]

        task_id = self.start_long_running(
            line, "catalog",
            {"scan_dir": scan_dir, "volume_tag": volume_tag,
             "kwargs": kwargs,
             "taskInterface": taskInterface}, scan_and_upload)
        return {"output": {"msg": "Thread Started", "task_id": task_id
                           }}


