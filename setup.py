from setuptools import setup

setup(
    name='lwe-pyloader',
    version='1.2.4',
    description='A simple, easy to use, multithreaded downloader '
    'with queuing.',
    long_description='For an overview and some examples, head over to '
    '`Github <https://github.com/linuxwhatelse/pyloader>`_',
    url='https://github.com/linuxwhatelse/pyloader',
    author='linuxwhatelse',
    author_email='info@linuxwhatelse.de',
    license='GPLv3',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
    keywords='downloader threaded queuing',
    py_modules=['pyloader'],
    install_requires=['requests'],
)
