"""A Server Backend for Updating Machines in Parallel to web server."""

import Queue
import threading
import signal
import subprocess
import shlex
import sys
import time
import os

import multiprocessing as mp

from functools import wraps
from multiprocessing import Process

UPDATE_SCRIPT = 'touch'

mgmt_storage = []


def handler(signal, frame):
    global mgmt_storage
    print 'handler: ', mgmt_storage
    while len(mgmt_storage) > 0:
        for process in mgmt_storage:
            process.stop()
        time.sleep(0.5)
        mgmt_storage = [_um for _um in mgmt_storage if _um.is_alive()]
    os._exit(0)

def pkiller_mgmt(cls):
    @wraps(cls)
    def wrapper(*args, **kwargs):
        obj = cls(*args, **kwargs)

        global mgmt_storage
        mgmt_storage.append(obj)
        print 'storage:', mgmt_storage
        return obj
    return wrapper

@pkiller_mgmt
class UpdateMgmt(Process):
    """An Update Thread manager."""
    def __init__(self):
        # Can't call super b/c UpdateMgmt is a function...
        #super(UpdateMgmt, self).__init__()
        Process.__init__(self)

        self.job_queue = mp.Queue()
        self.thread_pool = []

        self.subthread_queue = Queue.Queue()
        self.loc = mp.Lock()

        self.alive = mp.Value('b', True)
        self.start()

    def stop(self):
        """Stop the jobs gracefully."""
        with self.loc:
            self.alive.value = False

    def add_job(self, job_details):
        """Add a job to the schedule."""
        with self.loc:
            self.job_queue.put(job_details)

    def _add_logline(self, logline):
        """Add a line to the log."""
        server_time = time.strftime("%Y-%h-%d %H:%M:%S", time.gmtime())
        line = "{}: {}".format(server_time, logline)
        with self.loc:
            with open('logfile', 'a') as file_d:
                file_d.write(line)

    def get_loglines(self):
        """Get the log file."""
        with self.loc:
            with open('logfile', 'r') as file_d:
                return file_d.read()

    def _job_waiting(self):
        """There's a job waiting to be scheduled."""
        with self.loc:
            return self.job_queue.qsize() > 0

    def _full_pool(self):
        """Check if the thread pool has space."""
        return len(self.thread_pool) < 10

    def _empty_pool(self):
        """Check if the thread pool has space."""
        return len(self.thread_pool) == 0

    def _add_job(self):
        """Add a job to the thread pool."""
        with self.loc:
            job_target_details = self.job_queue.get()

        target = job_target_details.get("hostname")
        setup_details = job_target_details.get("setup_details_link")

        job = ScriptRunner(target, setup_details, self.subthread_queue)
        self.thread_pool.append(job)

    def _clean_dead_threads(self):
        """Clean up the dead threads and do the logging."""
        # Remove the dead threads.
        self.thread_pool = [_t for _t in self.thread_pool if _t.alive]

        while not self.subthread_queue.empty():
            # Do logging.
            sub_info = self.subthread_queue.get()
            host = sub_info.get("hostname")
            status = sub_info.get("status")
            line = "{} {} \n".format(host, status)
            self._add_logline(line)

    def run(self):
        print 'server_backend PID:', os.getpid()
        # Allow the object to die with grace.
        signal.signal(signal.SIGINT, handler)

        self.loc.acquire()
        while self.alive.value:
            self.loc.release()
            try:
                if self._full_pool() and self._job_waiting():
                    # If the pool has space and we have a job.
                    self._add_job()

                self._clean_dead_threads()

                if self._full_pool() or (not self._job_waiting()):
                    # Don't spin if we can't do work.
                    time.sleep(0.5)
            finally:
                # Take the lock before we loop around.
                self.loc.acquire()
        # Release the lock from the loop.
        self.loc.release()

        while not self._empty_pool():
            self._clean_dead_threads()
            time.sleep(0.5)


class ScriptRunner(threading.Thread):
    """Subthread update script runner."""
    def __init__(self, target, setup_details, shared_queue):
        super(ScriptRunner, self).__init__()
        self.target = target
        self.setup_details = setup_details
        self.alive = True
        self.start()

        if isinstance(shared_queue, Queue.Queue):
            self.shared_queue = shared_queue
        else:
            self.shared_queue = Queue.Queue()

    def get_cmd(self):
        # update_cmd = "{tool} {host} {link}"
        update_cmd = "{tool} {host}.{link}"
        return update_cmd.format(
            tool=UPDATE_SCRIPT,
            host=self.target,
            link=self.setup_details
        )

    def run(self):
        """Run the Update Script in a subthread."""
        try:
            subprocess.check_output(shlex.split(self.get_cmd()))
            subprocess.check_output(shlex.split("sleep 10"))
            result = {'hostname': self.target, 'status': 'SUCCESS'}
            self.shared_queue.put(result)
        except Exception:
            # We don't know what we caught.
            result = {'hostname': self.target, 'status': 'FAILURE'}
            self.shared_queue.put(result)
            raise
        finally:
            # Don't let a failure hang any waiting threads.
            self.alive = False


