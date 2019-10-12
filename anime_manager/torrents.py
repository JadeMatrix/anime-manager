import anime_manager.database

import itertools
import json
import logging
import os.path
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
sid_header = "X-Transmission-Session-Id"


class RPCError( Exception ):
    def __init__( self, server, result, message ):
        self.message = message
        Exception.__init__(
            self,
            "failed to perform RPC to {}: {}".format( server, result )
        )


def filter_paths_for_json( val ):
    """Recursively scan a structure for `pathlib.Paths`s and stringify them
    
    Calls `pathlib.Path.as_posix()` on each appropriate object.
    
    Args:
        val (any):  The structure to filter
    
    Returns:
        A copy of the same structure with `pathlib.Paths`s replaced by `str`s
    """
    
    try:
        return val.as_posix()
    except AttributeError:
        if (
               issubclass( type( val ), list )
            or issubclass( type( val ), tuple )
        ):
            return type( val )( filter_paths_for_json( v ) for v in val )
        elif issubclass( type( val ), set ):
            return list( filter_paths_for_json( v ) for v in val )
        elif issubclass( type( val ), dict ):
            return type( val )( (
                filter_paths_for_json( k ),
                filter_paths_for_json( v )
            ) for k, v in val.items() )
        else:
            return val


class TransmissionServer( object ):
    """Represents a single connection to a transmission server/daemon"""
    
    def __init__( self, location ):
        self.location = location
        self.session  = requests.Session()
        self.log      = logging.getLogger( "{}.{}".format(
            self.__class__.__module__,
            self.__class__.__name__
        ) )
    
    def rpc( self, method, arguments ):
        """Perform a Transmission RPC
        
        Args:
            method (str):       Transmission RPC method name
            arguments (str):    Arguments to pass in the RPC
        
        Returns:
            The contents of the "arguments" field in the response, parsed from
            JSON
        
        Raises:
            RPCError:   An error occurred regarding the contents of the payload
            requests.exceptions.RequestException:
                        An error occurred sending the request or receiving the
                        response
        """
        
        message = {
            "method"    : method,
            "arguments" : filter_paths_for_json( arguments ),
        }
        
        self.log.debug( "performing RPC to {}: {}".format(
            self.location,
            json.dumps( message, indent = 2 )
        ) )
        
        def do_rpc( url, data, retry = False ):
            response = self.session.post( url, data = json.dumps( data ) )
            if response.status_code == 409:
                if retry:
                    response.raise_for_status()
                else:
                    self.session.headers.update( {
                        sid_header : response.headers[ sid_header ]
                    } )
                    return do_rpc( url, data, True )
            return response.json()
        
        response_content = do_rpc(
            "http://{}/transmission/rpc".format( self.location ),
            message
        )
        
        self.log.debug( "RPC to {} got response: {}".format(
            self.location,
            json.dumps( response_content, indent = 2 )
        ) )
        
        if response_content[ "result" ] != "success":
            raise RPCError(
                self.location,
                response_content[ "result" ],
                message
            )
        
        return response_content[ "arguments" ]
    
    def remove_torrents( self, torrents, trash, dry_run = False ):
        """Execute a set of remove-torrent actions
        
        Args:
            torrents (iterable[str]):
                            Set of remove-torrent actions (torrent hashes)
            trash (pathlib.Path|None):
                            Trash directory (see `trash_item()`)
            dry_run (bool): Whether to skip actually executing actions
        """
        
        torrents = tuple( torrents )
        
        for hash in torrents:
            ( print if dry_run else log.debug )(
                "removing torrent {}".format( hash )
            )
        
        if not dry_run and torrents:
            locations = self.rpc(
                "torrent-get",
                {
                    "ids"    : torrents,
                    "fields" : ( "downloadDir", "name", ),
                }
            )[ "torrents" ]
            for location in locations:
                trash_item(
                    pathlib.Path( location[ "downloadDir" ] ) / location[ "name" ],
                    trash
                )
            self.rpc(
                "torrent-remove",
                {
                    "ids" : torrents,
                    "delete-local-data" : False,
                }
            )
    
    def source_torrents( self, torrents, trash, dry_run = False ):
        """Execute a set of re-source-torrent actions
        
        Args:
            torrents (iterable):
                            Set of re-source-torrent actions, each in the form:
                                {
                                    "hash"    : str,
                                    "sources" : { str, ... }
                                }
            trash (pathlib.Path|None):
                            Trash directory (see `trash_item()`)
            dry_run (bool): Whether to skip actually executing actions
        """
        for torrent in torrents:
            ( print if dry_run else log.debug )(
                "adding sources for torrent {!r} from {}".format(
                    torrent[ "hash" ],
                    tuple( torrent[ "sources" ] )
                )
            )
            log.warning( "{}.{}.source_torrents() not implemented".format(
                self.__class__.__module__,
                self.__class__.__name__
            ) )
    
    def move_torrents( self, torrents, trash, dry_run = False ):
        """Execute a set of move-torrent actions
        
        Args:
            torrents (iterable):
                            Set of move-torrent actions, each in the form:
                                {
                                    "hash"     : str,
                                    "location" : pathlib.Path,
                                }
            trash (pathlib.Path|None):
                            Trash directory (see `trash_item()`)
            dry_run (bool): Whether to skip actually executing actions
        """
        
        for torrent in torrents:
            (
                print if dry_run
                else log.debug
            )( "moving torrent {} to {!r}".format(
                torrent[ "hash" ],
                torrent[ "location" ].as_posix()
            ) )
            
            if not dry_run:
                self.rpc(
                    "torrent-set-location",
                    {
                        "ids"      : ( torrent[ "hash" ], ),
                        "location" : torrent[ "location" ].as_posix(),
                        "move"     : True,
                    }
                )
    
    def status_torrents( self, torrents, trash, dry_run = False ):
        """Execute a set of status-torrent actions
        
        Args:
            torrents (iterable):
                            Set of status-torrent actions, each in the form:
                                {
                                    "hash"    : str,
                                    "started" : bool,
                                }
            trash (pathlib.Path|None):
                            Trash directory (see `trash_item()`)
            dry_run (bool): Whether to skip actually executing actions
        """
        
        torrents = tuple( torrents )
        to_stop  = set()
        to_start = set()
        
        for torrent in torrents:
            start = torrent[ "started" ]
            
            ( print if dry_run else log.debug )(
                "setting torrent {} to {}".format(
                    torrent[ "hash" ],
                    "started" if start else "stopped"
                )
            )
            
            # Sorry about this
            add_to, other = (
                ( to_start, to_stop ) if start
                else ( to_stop, to_start ) 
            )
            if torrent[ "hash" ] in other:
                log.warning( "previous request to {} torrent {}, {}".format(
                    "stop" if start else "start",
                    hash,
                    "starting" if start else "stopping"
                ) )
                other.remove( torrent[ "hash" ] )
            add_to.add( torrent[ "hash" ] )
        
        if not dry_run and to_stop:
            self.rpc(
                "torrent-stop",
                { "ids" : to_stop, }
            )
        if not dry_run and to_start:
            self.rpc(
                "torrent-start",
                { "ids" : to_start, }
            )
    
    def add_torrents( self, torrents, trash, dry_run = False ):
        """Execute a set of add-torrent actions
        
        Args:
            torrents (iterable):
                            Set of add-torrent actions, each in the form:
                                {
                                    "sources"  : { str, ... },
                                    "location" : pathlib.Path,
                                }
            trash (pathlib.Path|None):
                            Trash directory (see `trash_item()`)
            dry_run (bool): Whether to skip actually executing actions
        """
        
        for torrent in torrents:
            sources = tuple( torrent[ "sources" ] )
            if len( sources ) != 1:
                log.warning(
                    "Got {} sources for a torrent, expected exactly 1".format(
                        len( source )
                    )
                )
            
            ( print if dry_run else log.debug )(
                "adding torrent to {!r} from {}".format(
                    torrent[ "location" ].as_posix(),
                    sources
                )
            )
            
            if not dry_run:
                self.rpc(
                    "torrent-add",
                    {
                        "filename"     : sources[ 0 ],
                        "download-dir" : torrent[ "location" ].as_posix(),
                    }
                )
    
    def torrent_name( self, torrents ):
        """Get the names of the specified torrents
        
        Args:
            torrents (iterable): Set of torrent hashes
        
        Returns:
            dict:   A map of the specified torrent hashes to their name
        """
        
        torrents = list( torrents )
        
        names = dict( zip(
            ( t[ "hashString" ], t[ "name" ] ) for t in self.rpc(
                "torrent-get",
                {
                    "ids"    : torrents,
                    "fields" : ( "hashString", "name", ),
                }
            )[ "torrents" ]
        ) )
        
        failed_hashes = set( torrents ) - set( names.keys() )
        if failed_hashes:
            raise RPCError(
                self.location,
                "success", # Server itself will report success
                "no such torrent(s): {}".format( ", ".join( failed_hashes ) )
            )
        else:
            return names


def replace_placeholder_filename( server, path ):
    """Replace a torrent download name placeholder in a path
    
    See `database.placeholder_filename()`
    
    Args:
        server (TransmissionServer):
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


def ensure_not_exists( item, trash ):
    """Ensure a path or file does not exist
    
    If the path or file exists, log a warning & trash it
    
    Args:
        item (pathlib.Path):        Item in question
        trash (pathlib.Path|None):  Trash directory (see `trash_item()`)
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


def remove_links( server, links, trash, dry_run = False ):
    """Execute a set of remove-symlink actions
    
    Args:
        server (TransmissionServer):
                        The Transmission server to use
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


def add_links( server, links, trash, dry_run = False ):
    """Execute a set of add-symlink actions
    
    Args:
        server (TransmissionServer):
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
                        Trash directory (see `trash_item()`)
        dry_run (bool): Whether to skip actually executing actions
    """
    
    for link in links:
        try:
            source = replace_placeholder_filename( server, link[ "source" ] )
            dest = link[ "dest" ].with_suffix( source.suffix )
        except RPCError:
            if dry_run:
                source = link[ "source" ]
                dest   = link[ "dest" ]
            else:
                raise
        
        ( print if dry_run else log.debug )( "adding link {!r} -> {!r}".format(
            dest.as_posix(),
            source.as_posix()
        ) )
        
        if not dry_run:
            ensure_not_exists( dest, trash )
            dest.parent.mkdir( parents = True, exist_ok = True )
            dest.symlink_to( source )


def execute_actions( server, actions, trash, dry_run = False ):
    """Execute a set of actions as output by `database.diff()`
    
    Args:
        server (TransmissionServer):
                        The Transmission server to use
        actions (dict): The set of actions
        trash (pathlib.Path|None):
                        Trash directory (see `trash_item()`)
        dry_run (bool): Whether to skip actually executing actions
    """
    remove_links  ( server, actions[ "links"    ][ "remove" ], trash, dry_run )
    server.remove_torrents( actions[ "torrents" ][ "remove" ], trash, dry_run )
    server.   add_torrents( actions[ "torrents" ][ "add"    ], trash, dry_run )
    server.source_torrents( actions[ "torrents" ][ "source" ], trash, dry_run )
    server.  move_torrents( actions[ "torrents" ][ "move"   ], trash, dry_run )
    server.status_torrents( actions[ "torrents" ][ "status" ], trash, dry_run )
    add_links     ( server, actions[ "links"    ][ "add"    ], trash, dry_run )
