pyloader - A simple python downloader
=====================================
[![Build Status](https://travis-ci.org/linuxwhatelse/pyloader.svg?branch=master)](https://travis-ci.org/linuxwhatelse/pyloader)

**pyloader** is a simple, easy to use, multi-threaded downloader with queuing support.

It is **NOT** a command-line utility but instead something you can (if you want) implement
in one (or more, I don't care :)) of your applications.

I was in need for such a thing and that's why I wrote it myself after only finding command-line utilities.  
(I haven't spent a lot of time searching though)

## Important notice
As of right now, this is **Beta**, so treat it as such ;)  
I added some unittests but there're still many more to go

## ToDo
Things to implement:
* More unittests
* Pause/Resume downloads

## Requirements
What you need:
* Python 2.7 / Python 3.4 and up
* The great python [requests](https://github.com/kennethreitz/requests) module

## Installation
Just run:  
```bash
pip install git+https://github.com/linuxwhatelse/pyloader
```

## Usage
The source has been commented quite well so at any point in time you might just:
```python
import pyloader
help(pyloader)
```

But to get you started, here are some examples :)
```python
import pyloader

def progress_callback(progress):
  # !!!IMPORTANT NOTE!!!
  # The callback will NOT be called within a separate thread
  # (to ensure consistancy) and WILL block the download
  # for as long as your callback runs!
  # Think twice about what you do in here.
  # Usually you just want to persist/visualize data.

  # Use ``help(pyloader.Progress)`` to know what's available
  print(progress.percent)
  
  # To cancel the download
  return True
  # If you don't want to cancel,
  return False
  # or return nothing at all
  

if __name__ == '__main__':
  # Create a loader instance
  dl = pyloader.Loader(
    max_concurrent = 3,
    progress_cb = progress_callback,
    update_intervall = 3
  )
  
  # Create a downloadable item
  # Make sure to read the docstrings via
  # help(pyloader.DLable)
  # for available arguments
  item = pyloader.DLable(
    url = 'http://download.thinkbroadband.com/5MB.zip',
    target_dir = '~/Downloads/',
  )
  
  # Queue an item or...
  dl.queue(item)
  # ...alternatively you can force a download,
  # ignoring ``max_concurrent``
  dl.download(item)
  
  # If you don't use a callback (to, if necessary, cancel a download),
  # you can stop one via:
  dl.stop(item)
  # or via its uid
  dl.stop(item.uid)

  # You can also clear the queue by
  dl.clear_queue()
  # and active items as well
  dl.clear_active()
  # though you'll never need the second one as there
  # are little to none cases where items are actually
  # stuck within the active queue

  # To check the downloaders state you can:
  print(dl.is_alive)  # True if both necessary main threads are still alive and kicking
  print(dl.is_active) # True if items are queued and/or downloading
  
  print(dl.queued) # Returns the amount of queued items
  print(dl.active) # Returns the amount of active/downloading items
  
  print(dl.max_concurrent) # The amount of maximum concurrent allowed downloads
  dl.max_concurrent = 5    # Set the amount up to 5 and starts new downloads (if any)

  # To stop all downloads and end the downloader just do:
  dl.exit()
  
  # Important to note here, queued/active items will **NOT** be persisted upon exit (or any other point in time)
  # It's up to you to keep track of the items ;)
```
Well, that should be enough to get you going (I hope)  
Happy coding! :)
