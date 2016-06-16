from context import pyloader

import os
import unittest

_current = os.path.dirname(os.path.abspath(__file__))

paths = {
    'writable'     : os.path.join(_current, 'downloads', 'write_access'),
    'not_writable' : os.path.join(_current, 'downloads', 'no_write_access')
}

class TestDLable(unittest.TestCase):

    def test_access_writable(self):
        try:
            pyloader.DLable(
                'http://url.doesnt.matter',
                paths['writable']
            )
            self.assertTrue(True)

        except IOError:
            self.assertTrue(False)

    def test_access_writable_none_existant(self):
        try:
            pyloader.DLable(
                'http://url.doesnt.matter',
                os.path.join(paths['writable'], 'sub')
            )
            self.assertTrue(True)

        except IOError:
            self.assertTrue(False)

    def test_access_not_writeable(self):
        self.assertRaises(IOError,
                          pyloader.DLable,
                          'http://url.doesnt.matter',
                          paths['not_writable'])

if __name__ == '__main__':
    unittest.main()
