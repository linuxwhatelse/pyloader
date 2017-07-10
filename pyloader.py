import sys
import os
import re
import time
import uuid
import json
import logging
import traceback

import threading

import requests

if sys.version_info >= (3, 0):
    import queue
    from urllib.parse import unquote

else:
    import Queue as queue
    from urllib import unquote

logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)


class DLable(object):
    uid = None
    url = None
    target_dir = None
    file_name = None
    cookies = None
    verify_ssl = True
    allow_redirects = True
    headers = {}
    chunk_size = 1024
    resolve_url = True

    def __init__(self, url, target_dir, file_name=None, uid=None, cookies=None,
                 verify_ssl=True, allow_redirects=True, headers=None,
                 chunk_size=1024, resolve_url=True):
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
            headers (dict): A dict representing headers to be added to the
                request. Defaults to None.
            chunk_size (int): The chunk size used for this downloadable.
                Defaults to `1024`
            resolve_url (bool): Whether or not the `url_resolve_cb` callback
                (supplied to the `Loader` class) should be called or not.
                Defaults to True.

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
        self.resolve_url = resolve_url

        if headers is not None:
            self.headers = headers

        # Test if the file (if any) is writable
        if self.file_name:
            _file = os.path.join(self.target_dir, self.file_name)
            if os.path.exists(_file):
                self._test_target(_file)

            else:
                self._test_target(self.target_dir)

        else:  # Test if the directory is writable
            self._test_target(self.target_dir)

    def __str__(self):
        return self.uid

    @property
    def target_file(self):
        return os.path.join(self.target_dir, self.file_name)

    def to_json(self):
        return json.dumps(self.__dict__)

    @classmethod
    def from_json(cls, data):
        return cls(**json.loads(data))

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
    FAILED = 'failed'
    PREPARING = 'preparing'
    EXISTED = 'file existed'
    IN_PROGRESS = 'in progress'
    CANCELED = 'canceled'
    FINISHED = 'finished'


class Progress:
    dlable = None
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

    time_spent = 0
    """int: Seconds spent for this download"""

    time_left = 0
    """int: Approximate seconds left for this download"""

    http_status = 0
    """int: HTTP status code received while retrieving the headers"""

    error = None
    """str: Result of traceback.format_exc() in case of an exception"""


class Loader(object):
    _exit = False

    _daemon = False

    _max_concurrent = None
    _progress_cb = None
    _url_resolve_cb = None
    _update_interval = None

    _queue_observer = None
    _active_observer = None

    _queue = queue.PriorityQueue()
    _queue_event = threading.Event()

    _active = queue.Queue()
    _active_event = threading.Event()

    _stop = list()

    def __init__(self, max_concurrent=3, progress_cb=None, update_interval=7,
                 daemon=False, url_resolve_cb=None):
        """Init for Loader

        Args:
            max_concurrent (int): Maximum amount of concurrent downloads.
                Set to 0 for unlimited
            progress_cb (func): Function to be called with progress updates
            update_interval (int): interval in sec. to call `progress_cb` with
                progress updates
            daemon (bool): Whether or not all spawned threads are daemon
                threads.
                The entire Python program exits when no alive non-daemon
                threads are left.
        """
        self._daemon = daemon

        self._max_concurrent = max_concurrent
        self._progress_cb = progress_cb
        self._url_resolve_cb = url_resolve_cb
        self._update_interval = update_interval

        self._queue_observer = threading.Thread(target=self._queue_observer,
                                                name='QueueObsThread')
        self._queue_observer.daemon = self._daemon

        self._active_observer = threading.Thread(target=self._active_observer,
                                                 name='ActiveObsThread')
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
        queued = self._queue.empty() and self._queue.unfinished_tasks == 0
        active = self._active.empty() and self._active.unfinished_tasks == 0

        return not (queued and active)

    @property
    def is_alive(self):
        """True if BOTH observer threads are alive, False otherwise"""
        return (self._queue_observer.is_alive() and
                self._active_observer.is_alive())

    def start(self):
        """Start this loader instance"""
        logger.info('Starting new pyloader instance')
        self._active_observer.start()
        self._queue_observer.start()

    def clear_queued(self):
        """Clears all queued items"""
        logger.info('Clearing queued items')
        while not self._queue.empty():
            self._queue.get_nowait()
            self._queue.task_done()

    def clear_active(self):
        """Clears all active items. It will NOT stop active downloads"""
        logger.info('Clearing active items')
        while not self._active.empty():
            self._active.get_nowait()
            self._active.task_done()

    def exit(self):
        """Gracefully stop all downloads and exit"""
        logger.info('Exit hast been requested')
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
                logger.info('Queuing {} with prio {}'.format(item[1],
                                                             item[0]))
                self._queue.put(item)

        else:
            logger.info('Queuing {} with prio {}'.format(dlable, -prio))
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
                logger.info('Downloading {}'.format(item))
                self._active.put(item)

        else:
            logger.info('Downloading {}'.format(dlable))
            self._active.put(dlable)

        self._active_event.set()

    def stop(self, uid=None, dlable=None):
        """Stops an active download

        Args:
            dlable (DLable): DLable which should be stopped
            uid (str): uid of a DLable which should be stopped
        """
        if not dlable and not uid:
            raise ValueError('At least one of `uid` or `dlable` '
                             'must be provided!')

        if not uid:
            uid = dlable.uid

        if uid not in self._stop:
            logger.info('Requesting stop for {}'.format(uid))
            self._stop.append(uid)

    def pause(self, uid=None, dlable=None):
        """Pauses an active download

        Args:
            dlable (DLable): DLable which should be paused
            uid (str): uid of a DLable which should be paused
        """
        if not dlable and not uid:
            raise ValueError('At least one of `uid` or `dlable` must be '
                             'provided!')

        raise NotImplementedError('Not implemented yet!')

    def resume(self, uid=None, dlable=None):
        """Resumes an paused download

        Args:
            dlable (DLable): DLable which should be resumed
            uid (str): uid of a DLable which should be resumed
        """
        if not dlable and not uid:
            raise ValueError('At least one of `uid` or `dlable` must be '
                             'provided!')

        raise NotImplementedError('Not implemented yet!')

    def _queue_observer(self):
        """Main loop which activates new downloads
        if conditions like max_concurrent match."""
        logger.info('Starting queue observer')
        while True:
            self._queue_event.wait()

            if self._exit:
                logger.info('Exiting queue observer')
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

                logger.info('Moving {} from queue to active'.format(item))
                self._active.put(item)
                self._active_event.set()

                self._queue.task_done()

            self._queue_event.clear()

    def _active_observer(self):
        """Main loop which starts new downloads."""
        logger.info('Starting active download observer')
        while True:
            self._active_event.wait()

            if self._exit:
                logger.info('Exiting active observer')
                return

            while not self._active.empty():
                try:
                    item = self._active.get_nowait()

                except queue.Empty:
                    break

                # Start download in new Thread
                logger.info('Starting new download {}'.format(item))
                _t = threading.Thread(target=self._get, args=[item])
                _t.daemon = self._daemon
                _t.start()

                time.sleep(0.25)

            self._active_event.clear()

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

            logger.info('Download {} finished'.format(dlable))
            self._active.task_done()

            logger.info('{} active and {} queued items remaining'.format(
                self.active, self.queued))

            # Notify the queue that this download finished
            # so new ones can be triggered (if available)
            self._queue_event.set()

        def _notify(progress):
            if (progress.status in [Status.FAILED, Status.EXISTED]
                    or progress.error):
                logger.error('Error while processing download {}'.format(
                    progress.dlable.uid))

                error = progress.error if progress.error else ''
                logger.error('  Reason: {} {}'.format(progress.status, error))

            if self._progress_cb:
                try:
                    return self._progress_cb(progress)
                except Exception:
                    logger.error('Failed executing progress callback for '
                                 '{}'.format(progress.dlable.uid),
                                 exc_info=True)
                    return True

            return False

        # Variables we need later on
        progress = Progress()
        progress.dlable = dlable
        progress.status = Status.PREPARING
        if _notify(progress):
            _finish()
            return

        started_at = time.time()
        last_updated = time.time() - self._update_interval

        # Get directory and filename
        _dir = dlable.target_dir
        _file = dlable.file_name

        # Create parent directories if they don't exist
        if not os.path.exists(_dir):
            try:
                os.makedirs(_dir)
            except FileExistsError:
                logger.warning('Directory already exists: {}'.format(_dir))

        try:
            url = dlable.url
            if self._url_resolve_cb is not None and dlable.resolve_url:
                # If we get a invalid url (or nothing), the requests
                # module will fail with a proper error-message.
                url = self._url_resolve_cb(url)

            # Create requests object as stream
            req = requests.get(
                url=url,
                allow_redirects=dlable.allow_redirects,
                verify=dlable.verify_ssl,
                cookies=dlable.cookies,
                headers=dlable.headers,
                stream=True
            )

        except Exception:
            progress.status = Status.FAILED
            progress.error = traceback.format_exc()
            _notify(progress)

            _finish()
            return

        progress.http_status = req.status_code

        # If the http status code is anything other than in the range of
        # 200 - 299, we skip
        if req.status_code != requests.codes.ok:
            progress.status = Status.FAILED
            progress.error = str(req.status_code)
            _notify(progress)

            _finish()
            return

        # Try to extract filename from headers if none was specified
        if not _file:
            dispos = req.headers.get('content-disposition')
            if dispos:
                _file = re.findall('filename=(.+)', dispos)

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
            content_length = int(content_length)
            progress.mb_total = content_length / 1024 / 1024

        # Check if the same file already exists and skip if it does
        if (os.path.exists(target) and
                os.path.getsize(target) == content_length):
            progress.status = Status.EXISTED
            _notify(progress)

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
                            progress.mb_current += ((float(len(chunk)) / 1024)
                                                    / 1024)
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

                            cancel = _notify(progress)

                    # Finally write our chunk. Yay! :)
                    f.write(chunk)

        except Exception:
            # If any form of error occurs, we catch it and report it
            # to the callback (if available)
            if os.path.exists(target):
                os.remove(target)

                progress.status = Status.FAILED
                progress.error = traceback.format_exc()
                _notify(progress)

        else:
            if self._exit or cancel:
                _notify(progress)

                if os.path.exists(target):
                    os.remove(target)

            else:
                # Call the callback a last time with finalized values
                progress.status = Status.FINISHED
                progress.percent = 100
                progress.mb_left = 0
                progress.mb_current = progress.mb_total

                _notify(progress)

        _finish()
