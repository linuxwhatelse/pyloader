import time
import pyloader


def progress_callback(progress):
    """!!! IMPORTANT !!!

    This callback will NOT be called from a subsequent thread but will use
    the downloads thread instead.
    This means the download blocks for as long as the callback is executed.

    Usually you only want to persist/visualize the progress.
    """
    # Use `help(pyloader.Progress)` to see all the goodies
    print(progress.dlable.file_name, '{0:.2f}%'.format(progress.percent))

    # `return True` if the download should be canceled
    return False


def url_resolver(item):
    """At times you may have urls that would expire while the item is queued.

    This callback will be called right before the download starts and allowes
    you to alter the `DLable` instance (and the url that goes along with it).
    """
    # item.url = 'http://new.url'
    return item


if __name__ == '__main__':
    # Create a loader instance
    loader = pyloader.Loader.get_loader()
    loader.configure(
        max_concurrent=3,
        update_interval=1,
        progress_cb=progress_callback,
        url_resolve_cb=url_resolver,
        daemon=False
    )

    # Start the loader
    # Make sure you know how the `daemon` flag
    # affects the liftime of your program
    loader.start()

    # Create downloadable items
    item1 = pyloader.DLable(
        url='http://download.thinkbroadband.com/5MB.zip',
        target_dir='./',
        file_name='item1.zip'
    )

    item2 = pyloader.DLable(
        url='http://download.thinkbroadband.com/5MB.zip',
        target_dir='./',
        file_name='item2.zip'
    )
    # Queue an item or...
    loader.queue(item1)

    # ...alternatively you can force a download,
    # ignoring `max_concurrent`
    loader.download(item2)

    # If you don't use a callback (which would allow you to cancel a
    # download if necessary), you can `stop` one too
    loader.stop(item1)
    # or via its uid
    loader.stop(item1.uid)

    # You can also clear all queued items
    loader.clear_queued()

    # True if both necessary main threads are still alive and kicking
    print('Is alive:', loader.is_alive())

    # True if items are queued and/or downloading
    print('Is active:', loader.is_active())

    # Amount of queued items
    print('Queued items:', loader.queued)

    # Amount of active/downloading items
    print('Active items:', loader.active)

    # The amount of maximum concurrent allowed downloads
    print('Max concurrent:', loader.max_concurrent)
    # Change the amount of max concurrent downloads
    # Will also trigger new downloads if necessary
    loader.max_concurrent = 5

    # How often the progress callback will be called in seconds
    print('Update interval:', loader.update_interval)
    # Change the interval
    loader.update_interval = 0.5

    # Wait for all downloads to finish
    while loader.is_active():
        time.sleep(0.25)

    # Exit downloader and stop all downloads
    # `pyloader` does NOT persist anything. This is up to you!
    loader.exit()
