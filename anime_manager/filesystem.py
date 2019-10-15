import logging
import pathlib
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
            / (
                pathlib.Path( *item.parts[ 1 : ] )
                if item.is_absolute() else item
            )
        )
        log.info( "trashing {!r} to {!r}".format(
            item.as_posix(),
            trashed_path.as_posix()
        ) )
        trashed_path.parent.mkdir( parents = True )
        item.rename( trashed_path )


def ensure_not_exists( item, trash ):
    """Ensure a path or file does not exist
    
    If the path or file exists, log a warning & trash it
    
    Args:
        item (pathlib.Path):        Item in question
        trash (pathlib.Path|None):  Trash directory (see
                                    `trash_item()`)
    """
    if item.exists():
        log.warning( "{!r} exists but should not, trashing".format(
            item.as_posix()
        ) )
        trash_item( item, trash )


def cleanup_empty_dirs( directories, dry_run = False ):
    """Recursively remove empty subdirectories in managed directories
    
    Args:
        directories (dict): The "directories" entry from a full database
        dry_run (bool):     Whether to skip actually removing directories
    """
    
    def cleanup( path ):
        if path.is_dir():
            children = False
            for child in path.iterdir():
                children = not cleanup( child ) or children
            if not children:
                ( print if dry_run else log.debug )(
                    "removing empty managed directory {!r}".format(
                        path.as_posix()
                    )
                )
                if not dry_run:
                    path.rmdir()
                return True
            else:
                return False
    
    for name, path in directories.items():
        if name == "media":
            continue
        cleanup( path )


def remove_links( links, trash, dry_run = False ):
    """Execute a set of remove-symlink actions
    
    Args:
        links (iterable[pathlib.Path]):
                        Set of remove-symlink actions (paths to remove)
        trash (pathlib.Path|None):
                        Trash directory (see `trash_item()`)
        dry_run (bool): Whether to skip actually executing actions
    """
    
    for link in links:
        ( print if dry_run else log.debug )(
            "removing link {!r}".format( link.as_posix() )
        )
        if not dry_run:
            if link.is_symlink():
                link.unlink()
            else:
                ensure_not_exists( link, trash )


def add_links( links, trash, dry_run = False ):
    """Execute a set of add-symlink actions
    
    Args:
        links (dict):   Set of add-symlink actions as a map of destinations to
                        sources, where the former will point to the latter
        trash (pathlib.Path|None):
                        Trash directory (see `trash_item()`)
        dry_run (bool): Whether to skip actually executing actions
    """
    
    for dest, source in links.items():
        ( print if dry_run else log.debug )( "adding link {!r} -> {!r}".format(
            dest  .as_posix(),
            source.as_posix()
        ) )
        
        if not dry_run:
            ensure_not_exists( dest, trash )
            dest.parent.mkdir( parents = True, exist_ok = True )
            dest.symlink_to( source )

