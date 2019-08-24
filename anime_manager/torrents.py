import anime_manager.database

import itertools
import json
import logging
import pathlib
import shutil
import re
import uuid

import requests


log = logging.getLogger( __name__ )

placeholder_pattern = re.compile( "".join(
    re.escape( s ) if not e % 2 else s
    for ( s, e ) in zip(
        re.split( r"(\{[^}]*\})", anime_manager.database.name_placeholder ),
        itertools.count()
    )
).format( "(" + anime_manager.database.hash_regex + ")" ) )
session = None
sid_header = "X-Transmission-Session-Id"


class RPCError( Exception ):
    def __init__( self, server, result, message ):
        self.message = message
        Exception.__init__(
            self,
            "failed to perform RPC to {}: {}".format( server, result )
        )


def rpc( server, method, arguments ):
    """Perform a Transmission RPC
    
    Args:
        server (str):       Address (+ port) of the Transmission server
        method (str):       Transmission RPC method name
        arguments (str):    Arguments to pass in the RPC
    
    Returns:
        The contents of the "arguments" field in the response, parsed from JSON
    
    Raises:
        RPCError:   An error occurred regarding the contents of the payload
        requests.exceptions.RequestException:
                    An error occurred sending the request or receiving the
                    response
    """
    
    global session
    if session is None:
        session = requests.Session()
    
    message = { "method" : method, "arguments" : arguments, }
    
    log.debug( "performing RPC to {}: {}".format(
        server,
        json.dumps( message, indent = 2 )
    ) )
    
    def do_rpc( url, data, retry = False ):
        response = session.post( url, data = json.dumps( data ) )
        if response.status_code == 409:
            if retry:
                response.raise_for_status()
            else:
                session.headers.update( {
                    sid_header : response.headers[ sid_header ]
                } )
                return do_rpc( url, data, True )
        return response.json()
    
    response_content = do_rpc(
        "http://{}/transmission/rpc".format( server ),
        message
    )
    
    if response_content[ "result" ] != "success":
        raise RPCError( server, response_content[ "result" ], message )
    
    return response_content[ "arguments" ]


def replace_placeholder_filename( server, path ):
    """Replace a torrent download name placeholder in a path
    
    See `database.placeholder_filename()`
    
    Args:
        server (str):           Address (+ port) of the Transmission server
        path (pathlib.Path):    Path potentially containing a torrent download
                                name placeholder
    
    Returns:
        pathlib.Path:   Proper path with placeholders replaced
    """
    
    new_path = []
    for part in path.parts:
        match = placeholder_pattern.match( part )
        if match:
            new_path.append( rpc(
                server,
                "torrent-get",
                {
                    "ids"    : ( match.group( 1 ), ),
                    "fields" : ( "name", ),
                }
            )[ "torrents" ][ 0 ][ "name" ] )
        else:
            new_path.append( part )
    
    return pathlib.Path( *new_path )


def trash_item( item, trash_directory ):
    """Move an item to the specified trash directory
    
    Offered as a safer alternative to simply deleting
    
    Args:
        item (pathlib.Path):    Item (file, directory) to trash
        trash_directory (pathlib.Path|None)
                                Trash directory; if None, item is removed
                                instead
    """
    
    if trash_directory is None:
        log.info( "deleting {!r}".format(
            item,
            trashed_path
        ) )
        if item.is_dir():
            shutil.rmtree( item )
        else:
            item.unlink()
    else:
        trashed_path = (
            trash_directory
            / str( uuid.uuid4() )
            / item
        )
        log.info( "trashing {!r} to {!r}".format(
            item,
            trashed_path
        ) )
        trashed_path.parent.mkdir( parents = True )
        item.rename( trashed_path )


def ensure_not_exists( item, trash ):
    """Ensure a path or file does not exist
    
    If the path or file exists, log a warning & trash it
    
    Args:
        item (pathlib.Path):        Item in question
        trash (pathlib.Path|None):  Trash directory (see `trash_item()`)
    """
    if item.exists():
        log.warning( "{!r} exists but should not, trashing".format(
            link.as_posix()
        ) )
        trash_item( link, trash )


def remove_links( server, links, trash ):
    """Execute a set of remove-symlink actions
    
    Args:
        server (str):   Address (+ port) of the Transmission server
        links (iterable[pathlib.Path]):
                        Set of remove-symlink actions (paths to remove)
        trash (pathlib.Path|None):
                        Trash directory (see `trash_item()`)
    """
    
    for link in links:
        log.debug( "removing link {!r}".format( link.as_posix() ) )
        if link.is_symlink():
            link.unlink()
        else:
            ensure_not_exists( link, trash )


def add_links( server, links, trash ):
    """Execute a set of add-symlink actions
    
    Args:
        server (str):   Address (+ port) of the Transmission server
        links (iterable):
                        Set of add-symlink actions, each in the form:
                            {
                                "source" : pathlib.Path,
                                "dest"   : pathlib.Path,
                            }
                        where "dest" will point to "source"
        trash (pathlib.Path|None):
                        Trash directory (see `trash_item()`)
    """
    
    for link in links:
        source = replace_placeholder_filename( server, link[ "source" ] )
        
        log.debug( "adding link {!r} -> {!r}".format(
            source.as_posix(),
            link[ "dest" ].as_posix()
        ) )
        
        ensure_not_exists( link[ "dest" ], trash )
        
        link[ "dest" ].parent.mkdir( parents = True, exist_ok = True )
        link[ "dest" ].symlink_to( source )


def remove_torrents( server, torrents, trash ):
    """Execute a set of remove-torrent actions
    
    Args:
        server (str):   Address (+ port) of the Transmission server
        torrents (iterable[str]):
                        Set of remove-torrent actions (torrent hashes)
        trash (pathlib.Path|None):
                        Trash directory (see `trash_item()`)
    """
    
    for hash in torrents:
        log.debug( "removing torrent {}".format( hash ) )
    
    if torrents:
        locations = rpc(
            server,
            "torrent-get",
            {
                "ids"    : ( match.group( 1 ), ),
                "fields" : ( "downloadDir", "name", ),
            }
        )[ "torrents" ]
        for location in locations:
            trash_item(
                pathlib.Path( location[ "downloadDir" ] ) / location[ "name" ],
                trash
            )
        rpc(
            server,
            "torrent-remove",
            {
                "ids" : tuple( torrents ),
                "delete-local-data" : False,
            }
        )


def resource_torrents( server, torrents, trash ):
    """Execute a set of re-source-torrent actions
    
    Args:
        server (str):   Address (+ port) of the Transmission server
        torrents (iterable):
                        Set of re-source-torrent actions, each in the form:
                            {
                                "hash"    : str,
                                "sources" : { str, ... }
                            }
        trash (pathlib.Path|None):
                        Trash directory (see `trash_item()`)
    """
    for torrent in torrents:
        log.debug( "adding sources for torrent {!r} from {}".format(
            torrent[ "hash" ],
            tuple( torrent[ "sources" ] )
        ) )


def move_torrents( server, torrents, trash ):
    """Execute a set of move-torrent actions
    
    Args:
        server (str):   Address (+ port) of the Transmission server
        torrents (iterable):
                        Set of move-torrent actions, each in the form:
                            {
                                "hash"     : str,
                                "location" : pathlib.Path,
                            }
        trash (pathlib.Path|None):
                        Trash directory (see `trash_item()`)
    """
    
    for torrent in torrents:
        log.debug( "moving torrent {} to {!r}".format(
            torrent[ "hash" ],
            torrent[ "location" ].as_posix()
        ) )
        
        rpc(
            server,
            "torrent-set-location",
            {
                "ids"      : ( torrent, ),
                "location" : torrent[ "location" ].as_posix(),
                "move"     : True,
            }
        )


def add_torrents( server, torrents, trash ):
    """Execute a set of add-torrent actions
    
    Args:
        server (str):   Address (+ port) of the Transmission server
        torrents (iterable):
                        Set of add-torrent actions, each in the form:
                            {
                                "sources"  : { str, ... },
                                "location" : pathlib.Path,
                            }
        trash (pathlib.Path|None):
                        Trash directory (see `trash_item()`)
    """
    
    for torrent in torrents:
        sources = tuple( torrent[ "sources" ] )
        if len( sources ) != 1:
            log.warning(
                "Got {} sources for a torrent, expected exactly 1".format(
                    len( source )
                )
            )
        
        log.debug( "adding torrent to {!r} from {}".format(
            torrent[ "location" ].as_posix(),
            sources
        ) )
        
        rpc(
            server,
            "torrent-add",
            {
                "filename"     : sources[ 0 ],
                "download-dir" : torrent[ "location" ].as_posix(),
            }
        )


def execute_actions( server, actions, trash ):
    """Execute a set of actions as output by `database.diff()`
    
    Args:
        server (str):   Address (+ port) of the Transmission server
        actions (dict): The set of actions
        trash (pathlib.Path|None):
                        Trash directory (see `trash_item()`)
    """
    remove_links     ( server, actions[ "links"    ][ "remove" ], trash )
    remove_torrents  ( server, actions[ "torrents" ][ "remove" ], trash )
    add_torrents     ( server, actions[ "torrents" ][ "add"    ], trash )
    resource_torrents( server, actions[ "torrents" ][ "source" ], trash )
    move_torrents    ( server, actions[ "torrents" ][ "move"   ], trash )
    add_links        ( server, actions[ "links"    ][ "add"    ], trash )
