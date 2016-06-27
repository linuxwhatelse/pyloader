import sys
import os
import re
import time
import uuid
import traceback

import threading

if sys.version_info >= (3, 0):
    import queue
    from urllib.parse import unquote

else:
    import Queue as queue
    from urllib import unquote

import requests


class DLable(object):
    uid    = None
    url    = None
    target_dir = None
    file_name  = None
    cookies = None
    verify_ssl = True
    allow_redirects = True
    chunk_size = 1024

    def __init__(self, url, target_dir, file_name=None, uid=None, cookies=None,
                 verify_ssl=True, allow_redirects=True, chunk_size=1024):
        """Init for DLable (short for Downloadable)

        Args:
            url (str): Url to a downloadable HTTP resource.
            target_dir (str): Writable, relative/absolute path to where the
                file should be stored.
            file_name (str): Optional file name for the downloaded resource.
                If `None`, the file name will be set to the one included
                in the HTTP response header (if available), a extracted name
                from the URL (only if a file extension exists) or to the `uid`.
                Defaults  to `None`.
            uid (str): Optional identifier for this downloadable item.
                If not given, a ``uuid.uuid4()`` will be generated.
            cookies (dict): Optional cookies to be set for ``requests.get``
                Defaults to `None`
            verify_ssl (bool): Whether or not to verify SSL certificates
                before downloading. Defaults to `True`.
            allow_redirects (bool): Whether or not to follow redirects
                for the specified ``url``. Defaults to `True`.
            chunk_size (int): The chunk size used for this downloadable.
                Defaults to `1024`

        Raises:
            IOError: If target file/folder is not writable
        """
        if uid:
            self.uid = uid

        else:
            self.uid = str(uuid.uuid4())

        self.url = url
        self.target_dir = os.path.abspath(os.path.expanduser(target_dir))
        self.file_name = file_name
        self.cookies = cookies
        self.verify_ssl = verify_ssl
        self.allow_redirects = allow_redirects
        self.chunk_size = chunk_size

        # Test if the file (if any) is writable
        if self.file_name:
            _file = os.path.join(self.target_dir, self.file_name)
            if os.path.exists(_file):
                self._test_target(_file)

            else:
                self._test_target(self.target_dir)

        else:  # Test if the directory is writable
            self._test_target(self.target_dir)

    def _test_target(self, path):
        """Helper which goes up in the directory hierarchy until a existing
        folder was found and checks whether or not we have write permissions"""
        if os.path.exists(path):
            if not os.access(path, os.W_OK):
                raise IOError('Target "%s" not writable!' % path)

        else:
            self._test_target(os.path.abspath(os.path.join(path, os.pardir)))

    def __eq__(self, other):
        return self.uid == other.uid

    def __lt__(self, other):
        return True


class Status:
    FAILED, PREPARING, EXISTED, IN_PROGRESS, CANCELED, FINISHED = range(6)


class Progress:
    dlable       = None
    """DLable: DLable associated with this progress update"""

    status = None
    """Status: The status this download is currently in"""

    mb_total = 0
    """float: Total megabytes for this item"""

    mb_current = 0
    """float: Currently downloaded megabytes for this item"""

    mb_left = 0
    """float: Megabytes left to download"""

    percent = 0
    """float: Download progress in percent"""

    time_spent   = 0
    """int: Seconds spent for this download"""

    time_left    = 0
    """int: Approximate seconds left for this download"""

    http_status  = 0
    """int: HTTP status code received while retrieving the headers"""

    error = None
    """str: Result of traceback.format_exc() in case of an exception"""


class Loader(object):
    _exit = False

    _daemon = False

    _max_concurrent  = None
    _progress_cb     = None
    _update_interval = None

    _queue_observer  = None
    _active_observer = None

    _queue = queue.PriorityQueue()
    _queue_event = threading.Event()

    _active = queue.Queue()
    _active_event = threading.Event()

    _stop = list()

    def __init__(self, max_concurrent=3, progress_cb=None, update_interval=7,
                 daemon=False):
        """Init for Loader

        Args:
            max_concurrent (int): Maximum amount of concurrent downloads.
                Set to 0 for unlimited
            progress_cb (func): Function to be called with progress updates
            update_interval (int): interval in sec. to call `progress_cb` with
                progress updates
            daemon (bool): Whether or not all spawned threads are daemon threads.
                The entire Python program exits when no alive non-daemon threads
                are left.
        """
        self._daemon = daemon

        self._max_concurrent  = max_concurrent
        self._progress_cb     = progress_cb
        self._update_interval = update_interval

        self._queue_observer  = threading.Thread(target=self._queue_observer)
        self._queue_observer.daemon = self._daemon

        self._active_observer = threading.Thread(target=self._active_observer)
        self._active_observer.daemon = self._daemon

    @property
    def max_concurrent(self):
        """Returns the maximum concurrent downloads"""
        return self._max_concurrent

    @max_concurrent.setter
    def max_concurrent(self, max_concurrent):
        """Sets the amount of maximum concurrent downloads
        and, if needed, triggers new ones"""
        self._max_concurrent = max_concurrent
        self._queue_event.set()

    @property
    def queued(self):
        """Returns the amount of unprocessed queued items"""
        return self._queue.unfinished_tasks

    @property
    def active(self):
        """Returns the amount of unprocessed (downloading) active items"""
        return self._active.unfinished_tasks

    @property
    def is_active(self):
        """True if items are queued/being processed, False otherwise"""
        return not ((self._queue.empty() and self._queue.unfinished_tasks == 0) and
                    (self._active.empty() and self._active.unfinished_tasks == 0))

    @property
    def is_alive(self):
        """True if BOTH observer threads are alive, False otherwise"""
        return (self._queue_observer.is_alive() and
                self._active_observer.is_alive())

    def start(self):
        """Start this loader instance"""
        self._active_observer.start()
        self._queue_observer.start()

    def clear_queued(self):
        """Clears all queued items"""
        while not self._queue.empty():
            self._queue.get_nowait()
            self._queue.task_done()

    def clear_active(self):
        """Clears all active items.
        However, it will NOT stop active downloads"""
        while not self._active.empty():
            self._active.get_nowait()
            self._active.task_done()

    def exit(self):
        """Gracefully stop all downloads and exit"""
        self._exit = True

        self.clear_queued()
        self.clear_active()

        self._queue_event.set()
        self._active_event.set()

    def kill(self):
        # Not sure if we actually want that
        raise NotImplementedError('Not implemented yet!')

    def queue(self, dlable, prio=-1):
        """Queues a new item to be downloaded.

        Args:
            dlable (DLable | List[Tuple(prio, DLable)]): Item(s) to be queued.
            prio (int): Queue priority of the item. The item with the highest
                prio will be downloaded first.
                Will be ignored in case ``dlable`` is a list
        """
        if type(dlable) == list:
            for item in dlable:
                self._queue.put(item)

        else:
            self._queue.put((-prio, dlable))

        self._queue_event.set()

    def unqueue(self, dlable):
        raise NotImplementedError('Not implemented yet!')

    def download(self, dlable):
        """Immediately starts a new download bypassing
        the queue and therefore `max_concurrent`.

        Args:
            dlable (DLable | List[DLable]): Item(s) to be downloaded.
        """
        if type(dlable) == list:
            for item in dlable:
                self._active.put(item)

        else:
            self._active.put(dlable)

        self._active_event.set()

    def stop(self, uid=None, dlable=None):
        """Stops an active download

        Args:
            dlable (DLable): DLable which should be stopped
            uid (str): uid of a DLable which should be stopped
        """
        if not dlable and not uid:
            raise ValueError('At least one of `uid` or `dlable` must be provided!')

        if not uid:
            uid = dlable.uid

        if uid not in self._stop:
            self._stop.append(uid)

    def pause(self, uid=None, dlable=None):
        """Pauses an active download

        Args:
            dlable (DLable): DLable which should be paused
            uid (str): uid of a DLable which should be paused
        """
        if not dlable and not uid:
            raise ValueError('At least one of `uid` or `dlable` must be provided!')

        raise NotImplementedError('Not implemented yet!')

    def resume(self, uid=None, dlable=None):
        """Resumes an paused download

        Args:
            dlable (DLable): DLable which should be resumed
            uid (str): uid of a DLable which should be resumed
        """
        if not dlable and not uid:
            raise ValueError('At least one of `uid` or `dlable` must be provided!')

        raise NotImplementedError('Not implemented yet!')

    def _queue_observer(self):
        """Main loop which activates new downloads
        if conditions like max_concurrent match."""

        while True:
            self._queue_event.wait()

            if self._exit:
                return

            # Move queued items to active state
            while not self._queue.empty():
                if (self._max_concurrent > 0 and
                        self._active.unfinished_tasks >= self._max_concurrent):
                    break

                try:
                    item = self._queue.get_nowait()[1]

                except queue.Empty:
                    break

                self._active.put(item)
                self._active_event.set()

                self._queue.task_done()

            self._queue_event.clear()

    def _active_observer(self):
        """Main loop which starts new downloads."""
        while True:
            self._active_event.wait()

            if self._exit:
                return

            while not self._active.empty():
                try:
                    item = self._active.get_nowait()

                except queue.Empty:
                    break

                # Start download in new Thread
                _t = threading.Thread(target=self._get, args=[item])
                _t.daemon = self._daemon
                _t.start()

            self._active_event.clear()

    def _notify(self, progress):
        if self._progress_cb:
            return self._progress_cb(progress)

        elif progress.error:
            print('Error while processing download with uid "%s"' %
                  progress.dlable.uid)
            print(progress.error)

        return False

    def _get(self, dlable):
        """Fetch a internet resource and propagate the process
        to the callback (if available) set via ``__init__``.

        Important!
        This method will NOT spawn a separate thread!!!

        Args:
            dlable (DLable): Item to be downloaded.
        """
        def _finish():
            # Just in case :)
            if dlable.uid in self._stop:
                self._stop.remove(dlable.uid)

            self._active.task_done()

            # Notify the queue that this download finished
            # so new ones can be triggered (if available)
            self._queue_event.set()

        # Variables we need later on
        progress = Progress()
        progress.dlable = dlable
        progress.status = Status.PREPARING
        if self._notify(progress):
            return

        started_at   = time.time()
        last_updated = time.time() - self._update_interval

        # Get directory and filename
        _dir  = dlable.target_dir
        _file = dlable.file_name

        # Create parent directories if they don't exist
        if not os.path.exists(_dir):
            os.makedirs(_dir)

        try:
            # Create requests object as stream
            req = requests.get(
                url = dlable.url,
                allow_redirects = dlable.allow_redirects,
                verify = dlable.verify_ssl,
                cookies = dlable.cookies,
                stream = True
            )

        except:
            progress.status = Status.FAILED
            progress.error  = traceback.format_exc()
            self._notify(progress)

            _finish()
            return

        progress.http_status = req.status_code

        # If the http status code is anything other than in the range of
        # 200 - 299, we skip
        if req.status_code < 200 or req.status_code > 299:
            progress.status = Status.FAILED
            self._notify(progress)

            _finish()
            return

        # Try to extract filename from headers if none was specified
        if not _file:
            dispos = req.headers.get('content-disposition')
            if dispos:
                _file  = re.findall('filename=(.+)', dispos)

        # Try to get a filename from the url itself
        # We only use this approach if a file-extension is given to make
        # sure it is actually the filename
        if not _file:
            _tmp_name = unquote(os.path.basename(req.url))
            if os.path.splitext(_tmp_name)[1]:
                _file = _tmp_name

        # Set filename to the downloadables uid as last resort
        if not _file:
            _file = dlable.uid

        # Full path to the file we'll be writing to
        target = os.path.join(_dir, _file)

        # Try and get the files content-length to calculate
        # a progress
        content_length = req.headers.get('content-length')
        if content_length:
            content_length    = int(content_length)
            progress.mb_total = content_length / 1024 / 1024

        # Check if the same file already exists and skip if it does
        if (os.path.exists(target) and
                os.path.getsize(target) == content_length):
            progress.status = Status.EXISTED
            self._notify(progress)

            _finish()
            return

        try:
            cancel = False

            progress.status = Status.IN_PROGRESS

            with open(target, 'wb+') as f:
                for chunk in req.iter_content(dlable.chunk_size):
                    # Check if we should cancel
                    if dlable.uid in self._stop:
                        self._stop.remove(dlable.uid)
                        cancel = True

                    if self._exit or cancel:
                        progress.status = Status.CANCELED
                        break

                    # Only do calculation if we actually have a callback
                    if self._progress_cb:
                        progress.time_spent = time.time() - started_at

                        # Calculate new progress
                        if progress.mb_total > 0:
                            # float cast is necessary for python2.7
                            progress.mb_current += (float(len(chunk)) / 1024) / 1024
                            progress.percent = (progress.mb_current * 100 /
                                                progress.mb_total)
                            progress.mb_left = (progress.mb_total -
                                                progress.mb_current)

                            if progress.mb_current > 0:
                                progress.time_left = int(progress.mb_left *
                                                         progress.time_spent /
                                                         progress.mb_current)

                        if time.time() > last_updated + self._update_interval:
                            last_updated = time.time()

                            cancel = self._notify(progress)

                    # Finally write our chunk. Yay! :)
                    f.write(chunk)

        except:
            # If any form of error occurs, we catch it and report it
            # to the callback (if available)
            if os.path.exists(target):
                os.remove(target)

                progress.status = Status.FAILED
                progress.error  = traceback.format_exc()
                self._notify(progress)

        else:
            if self._exit or cancel:
                self._notify(progress)

                if os.path.exists(target):
                    os.remove(target)

            else:
                # Call the callback a last time with finalized values
                progress.status     = Status.FINISHED
                progress.percent    = 100
                progress.mb_left    = 0
                progress.mb_current = progress.mb_total

                self._notify(progress)

        _finish()
