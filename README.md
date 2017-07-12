pyloader - A simple python downloader
=====================================
[![Build Status](https://travis-ci.org/linuxwhatelse/pyloader.svg?branch=master)](https://travis-ci.org/linuxwhatelse/pyloader)
[![pypi](https://img.shields.io/pypi/v/lwe-pyloader.svg)](https://pypi.python.org/pypi/lwe-pyloader)

**pyloader** is a simple, easy to use, multi-threaded downloader with queuing support.  

It is **NOT** a command-line utility but instead something you can (if you want) implement  
in one (or more, I don't care :)) of your applications.  

I wrote project-specific downloader a few times now and finally decided to create a proper module for it as  
I couldn't find an existing one (Haven't spent that much time searching though).  

## ToDo
Things to implement:
* More unittests
* Pause/Resume downloads

## Requirements
What you need:
* Python 2.7 / Python 3.4 and up
* The great python [requests](https://github.com/kennethreitz/requests) module

## Installation
### From pypi (recommanded)
```bash
pip install lwe-pyloader
```
### From source
```bash
git clone https://github.com/linuxwhatelse/pyloader
cd pyloader
python setup.py install
```
## Usage
The source has been commented quite well so at any point you might just:
```python
import pyloader
help(pyloader)
```

To get you started though, check the included [examples](examples).  
Happy coding! :)
