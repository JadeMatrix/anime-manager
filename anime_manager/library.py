import anime_manager.filesystem
import anime_manager.torrents

import itertools
import logging
import pathlib
import re


log = logging.getLogger( __name__ )

placeholder_pattern = re.compile( "".join(
    re.escape( s ) if not e % 2 else s
    for ( s, e ) in zip(
        re.split( r"(\{[^}]*\})", anime_manager.database.name_placeholder ),
        itertools.count()
    )
).format( "(" + anime_manager.database.hash_regex + ")" ) )


def replace_placeholder_filename( server, path ):
    """Replace a torrent download name placeholder in a path
    
    See `database.placeholder_filename()`
    
    Args:
        server (torrents.TransmissionServer):
                                The Transmission server to use
        path (pathlib.Path):    Path potentially containing a torrent download
                                name placeholder
    
    Returns:
        pathlib.Path:   Proper path with placeholders replaced
    """
    
    new_path = []
    for part in path.parts:
        match = placeholder_pattern.match( part )
        if match:
            hash = match.group( 1 )
            new_path.append( server.torrent_name( ( hash, ) )[ hash ] )
        else:
            new_path.append( part )
    
    return pathlib.Path( *new_path )


def ensure_not_exists( item, trash ):
    """Ensure a path or file does not exist
    
    If the path or file exists, log a warning & trash it
    
    Args:
        item (pathlib.Path):        Item in question
        trash (pathlib.Path|None):  Trash directory (see
                                    `filesystem.trash_item()`)
    """
    if item.exists():
        log.warning( "{!r} exists but should not, trashing".format(
            item.as_posix()
        ) )
        anime_manager.filesystem.trash_item( item, trash )


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


def remove_links( server, links, trash, dry_run = False ):
    """Execute a set of remove-symlink actions
    
    Args:
        server (torrents.TransmissionServer):
                        The Transmission server to use
        links (iterable[pathlib.Path]):
                        Set of remove-symlink actions (paths to remove)
        trash (pathlib.Path|None):
                        Trash directory (see `filesystem.trash_item()`)
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


def add_links( server, links, trash, dry_run = False ):
    """Execute a set of add-symlink actions
    
    Args:
        server (torrents.TransmissionServer):
                        The Transmission server to use
        links (iterable):
                        Set of add-symlink actions, each in the form:
                            {
                                "source" : pathlib.Path,
                                "dest"   : pathlib.Path,
                            }
                        where "dest" will point to "source" using the extension
                        of "source"
        trash (pathlib.Path|None):
                        Trash directory (see `filesystem.trash_item()`)
        dry_run (bool): Whether to skip actually executing actions
    """
    
    for link in links:
        try:
            source = replace_placeholder_filename( server, link[ "source" ] )
            dest = link[ "dest" ].with_suffix( source.suffix )
        except anime_manager.torrents.RPCError:
            if dry_run:
                source = link[ "source" ]
                dest   = link[ "dest" ]
            else:
                raise
        
        ( print if dry_run else log.debug )( "adding link {!r} -> {!r}".format(
            dest  .as_posix(),
            source.as_posix()
        ) )
        
        if not dry_run:
            ensure_not_exists( dest, trash )
            dest.parent.mkdir( parents = True, exist_ok = True )
            dest.symlink_to( source )


def execute_actions( server, actions, trash, dry_run = False ):
    """Execute a set of actions as output by `database.diff()`
    
    Args:
        server (torrents.TransmissionServer):
                        The Transmission server to use
        actions (dict): The set of actions
        trash (pathlib.Path|None):
                        Trash directory (see `filesystem.trash_item()`)
        dry_run (bool): Whether to skip actually executing actions
    """
    remove_links  ( server, actions[ "links"    ][ "remove" ], trash, dry_run )
    server.remove_torrents( actions[ "torrents" ][ "remove" ], trash, dry_run )
    server.   add_torrents( actions[ "torrents" ][ "add"    ], trash, dry_run )
    server.source_torrents( actions[ "torrents" ][ "source" ], trash, dry_run )
    server.  move_torrents( actions[ "torrents" ][ "move"   ], trash, dry_run )
    server.status_torrents( actions[ "torrents" ][ "status" ], trash, dry_run )
    add_links     ( server, actions[ "links"    ][ "add"    ], trash, dry_run )
