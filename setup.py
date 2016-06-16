from setuptools import setup, find_packages
from codecs import open
from os import path

here = path.abspath(path.dirname(__file__))

# Get the long description from the README file
with open(path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='pyloader',
    version='0.0.1',
    description='A simple, easy to use, multi-threaded downloader with queuing support.',
    long_description=long_description,
    url='https://github.com/linuxwhatelse/mapper',
    author='linuxwhatelse',
    author_email='info@linuxwhatelse.com',
    license='GPLv3',
    classifiers=[
        'Development Status :: 4 - Beta',

        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',

        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',

        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
    ],
    keywords='pyloader download multithreaded queue',
    py_modules=[
        'pyloader'
    ],
    install_requires=[
        'requests'
    ]
)
