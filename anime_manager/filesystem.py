import logging
import os.path
import shutil
import uuid


log = logging.getLogger( __name__ )


def trash_item( item, trash_directory ):
    """Move an item to the specified trash directory
    
    Offered as a safer alternative to simply deleting
    
    Args:
        item (pathlib.Path):    Item (file, directory) to trash
        trash_directory (pathlib.Path|None):
                                Trash directory; if None, item is removed
                                instead
    """
    
    if trash_directory is None:
        log.info( "deleting {!r}".format( item.as_posix() ) )
        if item.is_dir():
            shutil.rmtree( item )
        else:
            item.unlink()
    else:
        trashed_path = (
            trash_directory
            / str( uuid.uuid4() )
            / os.path.relpath( item )
        )
        log.info( "trashing {!r} to {!r}".format(
            item.as_posix(),
            trashed_path.as_posix()
        ) )
        trashed_path.parent.mkdir( parents = True )
        item.rename( trashed_path )
