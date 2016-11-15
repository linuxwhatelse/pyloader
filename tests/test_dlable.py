from context import pyloader

import os
import json
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

    def test_serialize_proper(self):
        item = pyloader.DLable(
            'http://url.doesnt.matter',
            paths['writable']
        )

        try:
            data = item.to_json()
            pyloader.DLable.from_json(data)

            self.assertTrue(True)

        except:
            self.assertTrue(False)

    def test_serialize_missing_required(self):
        item = pyloader.DLable(
            'http://url.doesnt.matter',
            paths['writable']
        )

        data = item.to_json()

        # Remove a required argument
        data = json.loads(data)
        del data['target_dir']
        data = json.dumps(data)

        self.assertRaises(TypeError,
                          pyloader.DLable.from_json, data)


if __name__ == '__main__':
    unittest.main()
