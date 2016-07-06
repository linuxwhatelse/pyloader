from context import pyloader

import os
import time
import unittest

_current = os.path.dirname(os.path.abspath(__file__))
target   = os.path.join(_current, 'downloads', 'write_access')

resources = {
    '5MB'   : 'http://download.thinkbroadband.com/5MB.zip',
    '10MB'  : 'http://download.thinkbroadband.com/10MB.zip',
    '20MB'  : 'http://download.thinkbroadband.com/20MB.zip',
    '50MB'  : 'http://download.thinkbroadband.com/50MB.zip',
    '100MB' : 'http://download.thinkbroadband.com/100MB.zip',
    '200MB' : 'http://download.thinkbroadband.com/200MB.zip',
    '512MB' : 'http://download.thinkbroadband.com/512MB.zip',
    '1GB'   : 'http://download.thinkbroadband.com/1GB.zip'
}


dummy = pyloader.DLable(resources['1GB'], target)


class TestLoader(unittest.TestCase):

    def test_properties(self):
        dl = pyloader.Loader(daemon=True)

        self.assertFalse(dl.is_active)
        self.assertFalse(dl.is_alive)

        self.assertIs(dl.queued, 0)
        self.assertIs(dl.active, 0)

        dl.queue(dummy)

        self.assertIs(dl.queued, 1)
        self.assertIs(dl.active, 0)

        self.assertTrue(dl.is_active)
        self.assertFalse(dl.is_alive)

        dl.start()

        # Give the loader some time to start the download
        time.sleep(1.0)

        self.assertIs(dl.queued, 0)
        self.assertIs(dl.active, 1)

        self.assertTrue(dl.is_active)
        self.assertTrue(dl.is_alive)

        dl.exit()

        # Give the loader some time to exit
        time.sleep(1.0)

        self.assertIs(dl.queued, 0)
        self.assertIs(dl.active, 0)

        self.assertFalse(dl.is_active)
        self.assertFalse(dl.is_alive)

    def test_callback_cancel(self):
        def _callback(progress):
            self.assertIsNotNone(progress.dlable)
            self.assertIsNone(progress.error)

            if progress.status == pyloader.Status.IN_PROGRESS:
                print('%s Kb/s' % progress.average_download_speed)
                self.assertGreater(progress.mb_total, 0)
                self.assertGreater(progress.mb_current, 0)
                self.assertGreater(progress.mb_left, 0)
                self.assertGreater(progress.percent, 0)
                self.assertGreater(progress.time_spent, 0)
                self.assertGreater(progress.time_left, 0)

                self.assertTrue(progress.http_status >= 200 and
                                progress.http_status <= 299)

                #return True

            else:
                return False

        dl = pyloader.Loader(
            progress_cb     = _callback,
            update_interval = 1,
            daemon          = True
        )

        dl.start()

        #dl.download(dummy)
        dummy1 = pyloader.DLable('https://r18---sn-h0j7sn7s.googlevideo.com/videoplayback?requiressl=yes&id=a5131b3b29f42a46&itag=22&source=webdrive&ttl=transient&app=texmex&ip=84.173.233.12&ipbits=32&expire=1467421871&sparams=expire,id,ip,ipbits,itag,mm,mn,ms,mv,nh,pl,requiressl,source,ttl&signature=7C6893DE1D32CF3F9CBDFB43AF64A0836086BD70.5ADB57B2E22D58FA2BC33682A11FB5DD0364418C&key=cms1&pl=19&cms_redirect=yes&mm=31&mn=sn-h0j7sn7s&ms=au&mt=1467411592&mv=m&nh=IgpwcjAxLm11YzA4KgkxMjcuMC4wLjE', target, 'dummy1.zip')
        dl.download(dummy1)


        # Wait for all downloads to end
        while dl.is_active:
            time.sleep(0.25)

        dl.exit()

    def test_stop(self):
        dl = pyloader.Loader(daemon=True)

        dummy1 = pyloader.DLable(resources['1GB'], target, 'dummy1.zip')
        dummy2 = pyloader.DLable(resources['1GB'], target, 'dummy2.zip')

        dl.queue(dummy1)
        dl.queue(dummy2)

        self.assertTrue(dl.is_active)
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

        self.assertFalse(dl.is_active)

        dl.exit()

if __name__ == '__main__':
    unittest.main()
