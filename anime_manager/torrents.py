import anime_manager.database

import itertools
import json
import logging
import pathlib
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
    """
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
    
    return {}


def replace_placeholder_filename( server, path ):
    """
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


def trash_item( trash_directory, item ):
    """
    """
    trashed_path = (
        trash_directory
        / str( uuid.uuid4() )
        / item
    )
    log.info( "trashing item {!r} to {!r}".format(
        item,
        trashed_path
    ) )
    trashed_path.parent.mkdir( parents = True )
    item.rename( trashed_path )


def remove_links( server, links, trash ):
    """
    """
    for link in links:
        log.debug( "removing link {!r}".format( link.as_posix() ) )
        
        if link.is_symlink():
            link.unlink()
        elif link.exists():
            log.warning(
                "attempt to remove link {!r} (not a link), trashing".format(
                    link.as_posix()
                )
            )
            trash_item( trash, link )
        else:
            log.debug( "not removing nonexistent link {!r}".format(
                link.as_posix()
            ) )


def add_links( server, links, trash ):
    """
    """
    for link in links:
        source = replace_placeholder_filename( server, link[ "source" ] )
        
        log.debug( "adding link {!r} -> {!r}".format(
            source.as_posix(),
            link[ "dest" ].as_posix()
        ) )
        
        link[ "dest" ].parent.mkdir( parents = True, exist_ok = True )
        link[ "dest" ].symlink_to( source )


def remove_torrents( server, torrents, trash ):
    """
    """
    for hash in torrents:
        log.debug( "removing torrent {}".format( hash ) )
    if torrents:
        rpc(
            server,
            "torrent-remove",
            {
                "ids" : tuple( torrents ),
                "delete-local-data" : False,
            }
        )


def resource_torrents( server, torrents, trash ):
    """
    """
    for torrent in torrents:
        log.debug( "adding sources for torrent {!r} from {}".format(
            torrent[ "hash" ],
            tuple( torrent[ "sources" ] )
        ) )


def move_torrents( server, torrents, trash ):
    """
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
    """
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
    """
    """
    remove_links     ( server, actions[ "links"    ][ "remove" ], trash )
    remove_torrents  ( server, actions[ "torrents" ][ "remove" ], trash )
    add_torrents     ( server, actions[ "torrents" ][ "add"    ], trash )
    resource_torrents( server, actions[ "torrents" ][ "source" ], trash )
    move_torrents    ( server, actions[ "torrents" ][ "move"   ], trash )
    add_links        ( server, actions[ "links"    ][ "add"    ], trash )
