import hashlib
import os
import sys
import threading
import time
import unittest

from context import pyloader

if sys.version_info[0] < 3:
    from mock import Mock
else:
    from unittest.mock import Mock

_current = os.path.dirname(os.path.abspath(__file__))
target = os.path.join(_current, 'downloads', 'write_access')

resources = {
    '5MB': 'http://download.thinkbroadband.com/5MB.zip',
    '10MB': 'http://download.thinkbroadband.com/10MB.zip',
    '20MB': 'http://download.thinkbroadband.com/20MB.zip',
    '50MB': 'http://download.thinkbroadband.com/50MB.zip',
    '100MB': 'http://download.thinkbroadband.com/100MB.zip',
    '200MB': 'http://download.thinkbroadband.com/200MB.zip',
    '512MB': 'http://download.thinkbroadband.com/512MB.zip',
    '1GB': 'http://download.thinkbroadband.com/1GB.zip'
}

headers = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/52.0.2743.82 Safari/537.36'
}
dummy = pyloader.DLable(resources['1GB'], target, headers=headers)


class TestLoader(unittest.TestCase):
    def test_instances(self):
        inst1 = pyloader.Loader.get_loader('inst1')
        inst2 = pyloader.Loader.get_loader('inst2')
        self.assertNotEqual(inst1, inst2)

        inst1_2 = pyloader.Loader.get_loader('inst1')
        inst2_2 = pyloader.Loader.get_loader('inst2')
        self.assertNotEqual(inst1_2, inst2_2)

        self.assertEqual(inst1, inst1_2)
        self.assertEqual(inst2, inst2_2)

        def _async():
            inst1_3 = pyloader.Loader.get_loader('inst1')
            inst2_3 = pyloader.Loader.get_loader('inst2')
            self.assertNotEqual(inst1_3, inst2_3)

            self.assertEqual(inst1, inst1_2, inst1_3)
            self.assertEqual(inst2, inst2_2, inst2_3)

        threading.Thread(target=_async).start()

    def test_configure(self):
        def _progress_cb1():
            pass  # noqa

        def _progress_cb2():
            pass  # noqa

        def _url_resolve_cb1():
            pass  # noqa

        def _url_resolve_cb2():
            pass  # noqa

        # Instantiate and configure loader
        inst1 = pyloader.Loader.get_loader()
        inst1.configure(max_concurrent=7, progress_cb=_progress_cb1,
                        update_interval=3, daemon=True,
                        url_resolve_cb=_url_resolve_cb1)

        # Test classmembers
        self.assertEqual(7, inst1.max_concurrent)
        self.assertEqual(3, inst1.update_interval)
        self.assertEqual(True, inst1._daemon)
        self.assertEqual(_progress_cb1, inst1._progress_cb)
        self.assertEqual(_url_resolve_cb1, inst1._url_resolve_cb)

        # Reconfigure not yet started instance
        inst1.configure(max_concurrent=3, progress_cb=_progress_cb2,
                        update_interval=1, daemon=False,
                        url_resolve_cb=_url_resolve_cb2)

        self.assertEqual(3, inst1.max_concurrent)
        self.assertEqual(1, inst1.update_interval)
        self.assertEqual(False, inst1._daemon)
        self.assertEqual(_progress_cb2, inst1._progress_cb)
        self.assertEqual(_url_resolve_cb2, inst1._url_resolve_cb)

        # Start loader
        inst1.start()

        # Reconfigure active loader
        with self.assertRaises(RuntimeError):
            inst1.configure(max_concurrent=7, progress_cb=_progress_cb1,
                            update_interval=3, daemon=True,
                            url_resolve_cb=_url_resolve_cb1)

        inst1.exit()

        self.assertNotEqual(7, inst1.max_concurrent)
        self.assertNotEqual(3, inst1.update_interval)
        self.assertNotEqual(True, inst1._daemon)
        self.assertNotEqual(_progress_cb1, inst1._progress_cb)
        self.assertNotEqual(_url_resolve_cb1, inst1._url_resolve_cb)

    def test_callback(self):
        mock = Mock(return_value=False)
        dummy1 = pyloader.DLable(resources['5MB'], target, 'dummy1.zip')
        dl = pyloader.Loader(progress_cb=mock, update_interval=1, daemon=True)
        dl.start()
        dl.download(dummy1)

        # Wait for all downloads to end
        while dl.is_active():
            time.sleep(0.25)

        dl.exit()

        mock.assert_called()

        os.remove(dummy1.target_file)

    def test_callback_cancel(self):
        mock = Mock(return_value=True)
        dummy1 = pyloader.DLable(resources['5MB'], target, 'dummy1.zip')
        dl = pyloader.Loader(progress_cb=mock, update_interval=1, daemon=True)
        dl.start()
        dl.download(dummy1)

        # Wait for all downloads to end
        while dl.is_active():
            time.sleep(0.25)

        dl.exit()

        mock.assert_called_once()

    def test_callback_overwrite(self):
        def _progress_cb(progress):
            return False

        def _url_resolve_cb(item):
            return item

        dl = pyloader.Loader(daemon=True)

        dummy1 = pyloader.DLable(resources['5MB'], target, 'dummy1.zip')
        dl.queue(dummy1)

        dl.start()

        with self.assertRaises(RuntimeError):
            dl.progress_cb = _progress_cb

        with self.assertRaises(RuntimeError):
            dl.url_resolve_cb = _url_resolve_cb

        while dl.is_active():
            time.sleep(0.25)

        dl.progress_cb = _progress_cb
        dl.url_resolve_cb = _url_resolve_cb

        dl.exit()

    def test_properties(self):
        dl = pyloader.Loader(daemon=True)

        self.assertFalse(dl.is_active())
        self.assertFalse(dl.is_alive())

        self.assertIs(dl.queued, 0)
        self.assertIs(dl.active, 0)

        dl.queue(dummy)

        self.assertIs(dl.queued, 1)
        self.assertIs(dl.active, 0)

        self.assertTrue(dl.is_active())
        self.assertFalse(dl.is_alive())

        dl.start()

        # Give the loader some time to start the download
        time.sleep(1.0)

        self.assertIs(dl.queued, 0)
        self.assertIs(dl.active, 1)

        self.assertTrue(dl.is_active())
        self.assertTrue(dl.is_alive())

        dl.exit()

        # Give the loader some time to exit
        time.sleep(1.0)

        self.assertIs(dl.queued, 0)
        self.assertIs(dl.active, 0)

        self.assertFalse(dl.is_active())
        self.assertFalse(dl.is_alive())

    def test_download_success(self):
        mock = Mock(return_value=False)
        dummy1 = pyloader.DLable(resources['5MB'], target, 'dummy1.zip')
        dl = pyloader.Loader(progress_cb=mock, update_interval=1, daemon=True)
        dl.start()
        dl.download(dummy1)

        # Wait for all downloads to end
        while dl.is_active():
            time.sleep(0.25)

        dl.exit()
        os.remove(dummy1.target_file)

        progress = mock.mock_calls[-1][1][0]
        self.assertEqual(progress.status, pyloader.Status.FINISHED)

    def test_download_incomplete(self):
        mock = Mock(return_value=False)
        dummy1 = pyloader.DLable(resources['5MB'], target, 'dummy1.zip',
                                 content_length=6291456)
        dl = pyloader.Loader(progress_cb=mock, update_interval=1, daemon=True)
        dl.start()
        dl.download(dummy1)

        # Wait for all downloads to end
        while dl.is_active():
            time.sleep(0.25)

        dl.exit()
        os.remove(dummy1.target_file)

        progress = mock.mock_calls[-1][1][0]
        self.assertEqual(progress.status, pyloader.Status.INCOMPLETE)

    def test_callback_cancel(self):
        def _callback(progress):
            self.assertIsNotNone(progress.dlable)
            self.assertIsNone(progress.error)

            if progress.status == pyloader.Status.IN_PROGRESS:
                self.assertGreater(progress.mb_total, 0)
                self.assertGreater(progress.mb_current, 0)
                self.assertGreater(progress.mb_left, 0)
                self.assertGreater(progress.percent, 0)
                self.assertGreater(progress.time_spent, 0)
                self.assertGreater(progress.time_left, 0)

                self.assertTrue(progress.http_status >= 200
                                and progress.http_status <= 299)

                return True

            else:
                return False

        dl = pyloader.Loader(progress_cb=_callback, update_interval=1,
                             daemon=True)

        dl.start()

        dl.download(dummy)

        # Wait for all downloads to end
        while dl.is_active():
            time.sleep(0.25)

        dl.exit()

    def test_callback_exception(self):
        def _callback(progress):
            raise Exception('Expected exception')

        dl = pyloader.Loader(progress_cb=_callback, update_interval=1,
                             daemon=True)

        dl.start()

        dl.download(dummy)

        # Wait for all downloads to end
        while dl.is_active():
            time.sleep(0.25)

        dl.exit()

    def test_url_resolve_cb(self):
        _url_resolved = threading.Event()

        def _url_resolver(item):
            _url_resolved.set()
            item.url = resources['1GB']
            return item

        dl = pyloader.Loader(update_interval=1, daemon=True,
                             url_resolve_cb=_url_resolver)
        dl.start()

        # Use normal url and not call the resolve callback
        dummy = pyloader.DLable(resources['1GB'], target, resolve_url=False)
        dl.download(dummy)

        time.sleep(1.0)
        dl.stop(dummy.uid)

        self.assertTrue(not _url_resolved.is_set())
        _url_resolved.clear()

        # Use "something-else" as url and let the callback resolve it
        dummy = pyloader.DLable('prot://some.url?id=123', target,
                                resolve_url=True)
        dl.download(dummy)

        time.sleep(1.0)
        dl.stop(dummy.uid)

        self.assertTrue(_url_resolved.is_set())
        _url_resolved.clear()

        # Wait for all downloads to end
        while dl.is_active():
            time.sleep(0.25)

        dl.exit()

    def test_stop(self):
        dl = pyloader.Loader(daemon=True)

        dummy1 = pyloader.DLable(resources['1GB'], target, 'dummy1.zip')
        dummy2 = pyloader.DLable(resources['1GB'], target, 'dummy2.zip')

        dl.queue(dummy1)
        dl.queue(dummy2)

        self.assertTrue(dl.is_active())
        self.assertIs(dl.active, 0)

        dl.start()

        # Make sure the download started
        time.sleep(1.0)
        self.assertIs(dl.active, 2)

        dl.stop(dummy1.uid)
        # Make sure the stop triggered
        time.sleep(1.0)
        self.assertIs(dl.active, 1)

        dl.stop(dummy2.uid)
        # Make sure the stop triggered
        time.sleep(1.0)
        self.assertIs(dl.active, 0)

        self.assertFalse(dl.is_active())

        dl.exit()

    def test_clear_queued(self):
        dl = pyloader.Loader(daemon=True)

        dummy1 = pyloader.DLable(resources['1GB'], target, 'dummy1.zip')
        dummy2 = pyloader.DLable(resources['1GB'], target, 'dummy2.zip')

        dl.queue(dummy1)
        dl.queue(dummy2)

        self.assertEqual(2, dl.queued)

        dl.clear_queued()

        self.assertEqual(0, dl.queued)

        dl.exit()

    def test_url_list(self):
        dl = pyloader.Loader(daemon=True)

        dummy = pyloader.DLable(
            [resources['5MB'], resources['5MB'], resources['5MB']],
            target,
            'dummy.zip',
            content_length=15728640,
        )

        dl.download(dummy)
        dl.start()

        while dl.is_active():
            time.sleep(0.25)

        target_file = os.path.join(target, 'dummy.zip')
        with open(target_file, 'rb') as f:
            self.assertEqual(
                hashlib.md5(f.read()).hexdigest(),
                'd7197443eb84599f02a36830a33f917f')

        os.remove(target_file)

        dl.exit()

    def test_header_list_url_str(self):
        with self.assertRaises(TypeError):
            pyloader.DLable(
                resources['5MB'],
                target,
                'dummy.zip',
                headers=[{}],
            )

    def test_header_list_url_list_uneven_args(self):
        with self.assertRaises(ValueError):
            pyloader.DLable(
                [resources['5MB']],
                target,
                'dummy.zip',
                headers=[{}, {}],
            )

    def test_url_headers_list(self):
        dl = pyloader.Loader(daemon=True)

        dummy = pyloader.DLable(
            [resources['5MB'], resources['5MB'], resources['5MB']],
            target,
            'dummy.zip',
            headers=[
                {
                    'Range': 'bytes=0-1048576'
                },
                {
                    'Range': 'bytes=0-2097152'
                },
                {
                    'Range': 'bytes=0-3145728'
                },
            ],
            content_length=6291456,
        )

        dl.download(dummy)
        dl.start()

        while dl.is_active():
            time.sleep(0.25)

        target_file = os.path.join(target, 'dummy.zip')
        with open(target_file, 'rb') as f:
            self.assertEqual(
                hashlib.md5(f.read()).hexdigest(),
                '037aabe7a96bc84c16c337da159b171b')

        os.remove(target_file)

        dl.exit()


if __name__ == '__main__':
    unittest.main()
