import json
import logging
import os
import re
import sys
import threading
import time
import traceback
import uuid

import requests

if sys.version_info >= (3, 0):
    import queue
    from urllib.parse import unquote

else:
    import Queue as queue
    from urllib import unquote

_lock = threading.RLock()
_instances = dict()

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
    headers = None
    chunk_size = 1024
    resolve_url = False
    content_length = None

    def __init__(self, url, target_dir, file_name=None, uid=None, cookies=None,
                 verify_ssl=True, allow_redirects=True, headers=None,
                 chunk_size=1024, resolve_url=False, content_length=None):
        """Init for DLable (short for Downloadable)

        Args:
            url (str|list): Url to a downloadable HTTP resource.
                If `list`, each url is considered a *chunk* and all chunks
                are combined together in order of the list.
            target_dir (str): Writable, relative/absolute path to where the
                file should be stored.
            file_name (str): Optional file name for the downloaded resource.
                If `None`, the file name will be set to the one included
                in the HTTP response header (if available), a extracted name
                from the URL (only if a file extension exists) or to the `uid`.
                Defaults to `None`.
            uid (str): Optional identifier for this downloadable item.
                If not given, a ``uuid.uuid4()`` will be generated.
            cookies (dict): Optional cookies to be set for ``requests.get``
                Defaults to `None`
            verify_ssl (bool): Whether or not to verify SSL certificates
                before downloading.
                Defaults to `True`.
            allow_redirects (bool): Whether or not to follow redirects
                for the specified ``url``.
                Defaults to `True`.
            headers (dict|list[dict]): List or dict representing headers to be
                added to the request.
                Defaults to None.
            chunk_size (int): The chunk size used for this downloadable.
                Defaults to `1024`
            resolve_url (bool): Whether or not the `url_resolve_cb` callback
                (supplied to the `Loader` class) should be called or not.
                Defaults to `False`.
            content_length (int): Expected size of the to be downloaded
                resource in bytes.
                This is used to calculate a progress and determin whether a
                already existing file should be overwritten or not.

                For single urls the resources http header will be parsed for
                the *content-length* attribute which may or may not exist.

                For multiple urls the sum of all needs to be provided if
                progress and file checking is desired.

                Defaults to None.


        Raises:
            IOError: If target file/folder is not writable
            TypeError: If headers is a list but url isn't
            ValueError: if url and headers list are of different size
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

        if content_length:
            self.content_length = content_length

        if headers is not None:
            self.headers = headers
            if isinstance(headers, list):
                if not isinstance(self.url, list):
                    raise TypeError('If headers is a list, url has to be too.')

                if len(self.url) != len(self.headers):
                    raise ValueError(
                        'url and headers list have to be of the same size.')

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
        if not isinstance(other, DLable):
            return False

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
    INCOMPLETE = 'incomplete'

    @property
    def ok(self):
        """Returns a list of status considered to be successful"""
        return [self.FINISHED]

    @property
    def not_ok(self):
        """Returns a list of status considered to be NOT successful"""
        return [self.FAILED, self.EXISTED, self.CANCELED]

    @property
    def active(self):
        """Returns a list of status considered to be still active"""
        return [self.PREPARING, self.IN_PROGRESS]


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
    _lock = threading.RLock()
    _dl_lock = threading.RLock()
    _name = None
    _configured = False

    _exit = False

    _daemon = False

    _max_concurrent = None
    _update_interval = None
    _progress_cb = None
    _url_resolve_cb = None

    _queue_observer_thread = None
    _active_observer_thread = None

    _queue = queue.PriorityQueue()
    _queue_event = threading.Event()

    _active = queue.Queue()
    _active_event = threading.Event()

    _stop = list()

    def __init__(self, max_concurrent=3, progress_cb=None, update_interval=7,
                 daemon=False, url_resolve_cb=None):
        """Init for Loader.

        Example:
            loader = Loader.get_loader('awesome_loader')
            loader.configure(...)

            # Whenever you need this loader instances
            loader = Loader.get_loader('awesome_loader')
            loader.queue(...)

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
            url_resolve_cb (func): Function be be called to get a downloadable
                url. The belonging `DLable` instance will be passed.

        """
        self.configure(max_concurrent, progress_cb, update_interval, daemon,
                       url_resolve_cb)

    @staticmethod
    def get_loader(name=__name__):
        """Return a Loader instance with the given name. If the name already
           exist return its instance.

           Does not work if a Loader was created via its constructor.

           Using `Loader.get_loader()` is the prefered way.

           Use `configure(...)` to configure a instance.

        Args:
            name (str): Name of the instance
        """
        rv = None
        if not isinstance(name, str):
            raise TypeError('A pyloader name must be a string')

        with _lock:
            if name in _instances:
                rv = _instances[name]

            else:
                rv = Loader()
                _instances[name] = rv

            rv._name = name

        return rv

    def configure(self, max_concurrent=3, progress_cb=None, update_interval=7,
                  daemon=False, url_resolve_cb=None):
        """Configure this Loader instance.

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
            url_resolve_cb (func): Function be be called to get a downloadable
                url. The belonging `DLable` instance will be passed.

        Raises:
            RuntimeError: If this instance was already configured and started.
        """
        if self._configured and self.is_alive():
            raise RuntimeError('Cannot reconfigure already started instance.')

        with self._lock:
            self._configured = True

            self.max_concurrent = max_concurrent
            self.update_interval = update_interval
            self.progress_cb = progress_cb
            self.url_resolve_cb = url_resolve_cb

            self._daemon = daemon

            self._queue_observer_thread = threading.Thread(
                target=self._queue_observer, name='QueueObsThread')
            self._queue_observer_thread.daemon = self._daemon

            self._active_observer_thread = threading.Thread(
                target=self._active_observer, name='ActiveObsThread')
            self._active_observer_thread.daemon = self._daemon

    @property
    def max_concurrent(self):
        """Returns the amount of maximum concurrent downloads"""
        return self._max_concurrent

    @max_concurrent.setter
    def max_concurrent(self, max_concurrent):
        """Sets the amount of maximum concurrent downloads
        and, if required, starts new ones"""
        self._max_concurrent = max_concurrent
        self._queue_event.set()

    @property
    def update_interval(self):
        """Returns the update interval in seconds"""
        return self._update_interval

    @update_interval.setter
    def update_interval(self, interval):
        """Set the update interval in sec. defining how often the progress
           callback should be called."""
        self._update_interval = interval

    @property
    def progress_cb(self):
        """Returns the currently configured progress callback"""
        return self._progress_cb

    @progress_cb.setter
    def progress_cb(self, callback):
        """Sets the progress callback.

           Raises:
                RuntimeError: If items are downloading/queued
        """
        if self.is_active():
            raise RuntimeError('Cannot change callback while loader is active')

        self._progress_cb = callback

    @property
    def url_resolve_cb(self):
        """Returns the currently configured url resolver callback"""
        return self._url_resolve_cb

    @url_resolve_cb.setter
    def url_resolve_cb(self, callback):
        """Sets the url resolver callback.

           Raises:
                RuntimeError: If items are downloading/queued
        """
        if self.is_active():
            raise RuntimeError('Cannot change callback while loader is active')

        self._url_resolve_cb = callback

    @property
    def queued(self):
        """Returns the amount of unprocessed queued items"""
        return self._queue.unfinished_tasks

    @property
    def active(self):
        """Returns the amount of unprocessed (downloading) active items"""
        return self._active.unfinished_tasks

    def is_active(self):
        """True if items are queued/being processed, False otherwise"""
        queued = self._queue.empty() and self._queue.unfinished_tasks == 0
        active = self._active.empty() and self._active.unfinished_tasks == 0

        return not (queued and active)

    def is_alive(self):
        """True if BOTH observer threads are alive, False otherwise"""
        if (self._queue_observer_thread is None
                or self._queue_observer_thread.is_alive() is False):
            return False

        if (self._queue_observer_thread is None
                or self._active_observer_thread.is_alive() is False):
            return False

        return True

    def start(self):
        """Start this loader instance"""
        logger.info('Starting new pyloader instance')
        with self._lock:
            self._active_observer_thread.start()
            self._queue_observer_thread.start()

    def clear_queued(self):
        """Clears all queued items"""
        logger.info('Clearing queued items')
        with self._lock:
            while not self._queue.empty():
                self._queue.get_nowait()
                self._queue.task_done()

    def exit(self):
        """Gracefully stop all downloads and exit"""
        logger.info('Exit hast been requested')
        with self._lock:
            self._exit = True

            self.clear_queued()

            self._queue_event.set()
            self._active_event.set()

    def kill(self):
        # Not sure if we actually want that
        raise NotImplementedError('Not implemented yet!')

    def queue(self, dlable, prio=None):
        """Queues a new item to be downloaded.

        Args:
            dlable (DLable | List[Tuple(prio, DLable)]): Item(s) to be queued.
            prio (int): Queue priority of the item. The item with the highest
                prio will be downloaded first.
                Will be ignored in case ``dlable`` is a list
        """
        with self._lock:
            if type(dlable) == list:
                for item in dlable:
                    logger.info('Queuing {} with prio {}'.format(
                        item[1], item[0]))
                    self._queue.put(item)

            else:
                if prio is None:
                    prio = self.queued + 1

                logger.info('Queuing {} with prio {}'.format(dlable, prio))
                self._queue.put((prio, dlable))

            self._queue_event.set()

    def unqueue(self, dlable):
        raise NotImplementedError('Not implemented yet!')

    def download(self, dlable):
        """Immediately starts a new download bypassing
        the queue and therefore `max_concurrent`.

        Args:
            dlable (DLable | List[DLable]): Item(s) to be downloaded.
        """
        with self._lock:
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

        with self._lock:
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

            self._active_event.clear()

    def _get(self, dlable):
        """Fetch a internet resource and propagate the process
        to the callback (if available) set via ``__init__``.

        Important!
        This method will NOT spawn a separate thread!!!

        Args:
            dlable (DLable): Item to be downloaded.
        """
        def _finish(dlable, progress):
            # Just in case :)
            if dlable.uid in self._stop:
                self._stop.remove(dlable.uid)

            logger.info('Download {} ended with status '
                        '"{}"'.format(dlable, progress.status))

            self._active.task_done()
            self._queue_event.set()

            logger.info('{} active and {} queued items remaining'.format(
                self.active, self.queued))

        def _propagate(progress):
            cancel = False

            if self._progress_cb:
                try:
                    cancel = self._progress_cb(progress)
                except Exception as e:
                    logger.error('Progress callback failed for {}'.format(
                        progress.dlable.uid))
                    logger.error('  Reason: {}'.format(str(e)))
                    return True

            if (progress.status in [Status.FAILED, Status.EXISTED]
                    or progress.error):
                error = progress.error if progress.error else ''
                logger.error('Error while processing download {}'.format(
                    progress.dlable.uid))
                logger.error('  Reason: {} {}'.format(progress.status, error))
                return True

            return cancel

        logger.info('{} active and {} queued items remaining'.format(
            self.active, self.queued))

        def _is_http_status_ok(req, progress):
            # If the http status code is anything other than in the range of
            # 200 - 299, we skip
            if (req.status_code != requests.codes.ok
                    and req.status_code != requests.codes.partial):
                progress.status = Status.FAILED
                progress.error = str(req.status_code)
                _propagate(progress)

                _finish(dlable, progress)
                return False
            return True

        # Prepwork only with active lock
        with self._dl_lock:
            # Variables we need later on
            progress = Progress()
            progress.dlable = dlable
            progress.status = Status.PREPARING
            if _propagate(progress):
                _finish(dlable, progress)
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
            if self._url_resolve_cb is not None and dlable.resolve_url:
                # If we get a invalid url (or nothing), the requests
                # module will fail with a proper error-message.
                dlable = self.url_resolve_cb(dlable)

            # Create requests object as stream
            req = _MyRequest(url=dlable.url,
                             allow_redirects=dlable.allow_redirects,
                             verify=dlable.verify_ssl, cookies=dlable.cookies,
                             headers=dlable.headers)

        except Exception:
            progress.status = Status.FAILED
            progress.error = traceback.format_exc()
            _propagate(progress)

            _finish(dlable, progress)
            return

        progress.http_status = req.status_code

        if not _is_http_status_ok(req, progress):
            return

        # Try to extract filename from headers if none was specified
        if not _file:
            _file = req.filename

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
        if dlable.content_length:
            content_length = dlable.content_length
        else:
            content_length = req.content_length

        if content_length:
            content_length = int(content_length)
            progress.mb_total = content_length / 1024 / 1024

        # Check if the same file already exists and skip if it does
        if (os.path.exists(target)
                and os.path.getsize(target) == content_length):
            progress.status = Status.EXISTED
            _propagate(progress)

            _finish(dlable, progress)
            return

        try:
            cancel = False
            progress.status = Status.IN_PROGRESS

            with open(target, 'wb+') as f:
                for chunk in req.iter_content(dlable.chunk_size):
                    if not _is_http_status_ok(req, progress):
                        return

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
                            progress.mb_current += (
                                (float(len(chunk)) / 1024) / 1024)
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

                            cancel = _propagate(progress)

                    # Finally write our chunk. Yay! :)
                    f.write(chunk)

        except Exception:
            # If any form of error occurs, we catch it and report it
            # to the callback (if available)
            if os.path.exists(target):
                os.remove(target)

                progress.status = Status.FAILED
                progress.error = traceback.format_exc()
                _propagate(progress)

        else:
            if self._exit or cancel:
                _propagate(progress)

                if os.path.exists(target):
                    os.remove(target)

            else:
                if (content_length
                        and os.path.getsize(target) < content_length):
                    progress.status = Status.INCOMPLETE
                    _propagate(progress)

                else:
                    # Call the callback a last time with finalized values
                    progress.status = Status.FINISHED
                    progress.percent = 100
                    progress.mb_left = 0
                    progress.mb_current = progress.mb_total

                    _propagate(progress)

        _finish(dlable, progress)


class _MyRequest:
    urls = None
    headers = None
    has_multiple = False
    has_multiple_headers = False

    _req = None

    def __init__(self, url, allow_redirects, verify, cookies, headers):
        self.headers = headers

        self.has_multiple = isinstance(url, list)
        self.has_multiple_headers = isinstance(headers, list)

        if self.has_multiple:
            self.urls = url
            url = self.urls.pop(0)

        self.requests_args = {
            'allow_redirects': allow_redirects,
            'verify': verify,
            'cookies': cookies,
            'stream': True
        }

        if self.has_multiple_headers:
            headers = self.headers.pop(0)

        self._req = requests.get(url=url, headers=headers,
                                 **self.requests_args)

    @property
    def url(self):
        return self._req.url

    @property
    def status_code(self):
        return self._req.status_code

    @property
    def filename(self):
        if self.has_multiple:
            return None

        dispos = self._req.headers.get('content-disposition')
        if dispos:
            return re.findall('filename=(.+)', dispos)

    @property
    def content_length(self):
        if self.has_multiple:
            return None

        return self._req.headers.get('content-length')

    def iter_content(self, chunk_size):
        for chunk in self._req.iter_content(chunk_size):
            yield chunk

        if not self.has_multiple:
            return

        for url in self.urls:
            headers = self.headers
            if self.has_multiple_headers:
                headers = self.headers.pop(0)

            self._req = requests.get(url=url, headers=headers,
                                     **self.requests_args)
            for chunk in self._req.iter_content(chunk_size):
                yield chunk
