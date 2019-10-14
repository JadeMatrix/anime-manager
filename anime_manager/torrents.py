import anime_manager.database
import anime_manager.filesystem

import json
import logging
import os.path
import pathlib

import requests


log = logging.getLogger( __name__ )

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
                            Trash directory (see `filesystem.trash_item()`)
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
                anime_manager.filesystem.trash_item(
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
                                    "hash"   : str,
                                    "source" : str
                                }
            trash (pathlib.Path|None):
                            Trash directory (see `filesystem.trash_item()`)
            dry_run (bool): Whether to skip actually executing actions
        """
        for torrent in torrents:
            ( print if dry_run else log.debug )(
                "adding source for torrent {!r} from {}".format(
                    torrent[ "hash" ],
                    torrent[ "source" ]
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
                            Trash directory (see `filesystem.trash_item()`)
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
                            Trash directory (see `filesystem.trash_item()`)
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
                                    "source"   : str,
                                    "location" : pathlib.Path,
                                }
            trash (pathlib.Path|None):
                            Trash directory (see `filesystem.trash_item()`)
            dry_run (bool): Whether to skip actually executing actions
        """
        
        for torrent in torrents:
            ( print if dry_run else log.debug )(
                "adding torrent to {!r} from {}".format(
                    torrent[ "location" ].as_posix(),
                    torrent[ "source" ]
                )
            )
            
            if not dry_run:
                self.rpc(
                    "torrent-add",
                    {
                        "filename"     : torrent[ "source" ],
                        "download-dir" : torrent[ "location" ].as_posix(),
                    }
                )
    
    def torrent_names( self, torrents ):
        """Get the names of the specified torrents
        
        Args:
            torrents (iterable): Set of torrent hashes
        
        Returns:
            dict:   A map of the specified torrent hashes to their name
        """
        
        torrents = list( torrents )
        
        names = dict(
            ( t[ "hashString" ], t[ "name" ] ) for t in self.rpc(
                "torrent-get",
                {
                    "ids"    : torrents,
                    "fields" : ( "hashString", "name", ),
                }
            )[ "torrents" ]
        )
        
        failed_hashes = set( torrents ) - set( names.keys() )
        if failed_hashes:
            raise RPCError(
                self.location,
                "success", # Server itself will report success
                "no such torrent(s): {}".format( ", ".join( failed_hashes ) )
            )
        else:
            return names
    
    def torrent_files( self, torrents ):
        """Get the names of files included in the specified torrents
        
        Args:
            torrents (iterable): Set of torrent hashes
        
        Returns:
            dict:   A map of the specified torrent hashes to a list of filenames
                    as `pathlib.Path`s
        """
        
        torrents = list( torrents )
        
        files = dict(
            (
                t[ "hashString" ],
                list( pathlib.Path( f[ "name" ] ) for f in t[ "files" ] )
            ) for t in self.rpc(
                "torrent-get",
                {
                    "ids"    : torrents,
                    "fields" : ( "hashString", "files", ),
                }
            )[ "torrents" ]
        )
        
        failed_hashes = set( torrents ) - set( files.keys() )
        if failed_hashes:
            raise RPCError(
                self.location,
                "success", # Server itself will report success
                "no such torrent(s): {}".format( ", ".join( failed_hashes ) )
            )
        else:
            return files
