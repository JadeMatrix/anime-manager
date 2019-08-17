import logging

import requests


log = logging.getLogger( __name__ )


def remove_links( links ):
    """
    """
    for link in links:
        log.debug( "Removing link {!r}".format( link.as_posix() ) )


def add_links( links ):
    """
    """
    for link in links:
        log.debug( "Adding link {!r} -> {!r}".format(
            link[ "source" ].as_posix(),
            link[ "dest" ].as_posix()
        ) )


def remove_torrents( torrents ):
    """
    """
    for torrent in torrents:
        log.debug( "Removing torrent {}".format( torrent ) )


def resource_torrents( torrents ):
    """
    """
    for torrent in torrents:
        log.debug( "Adding sources for torrent {!r} from {}".format(
            torrent[ "hash" ],
            tuple( torrent[ "sources" ] )
        ) )


def move_torrents( torrents ):
    """
    """
    for torrent in torrents:
        log.debug( "Moving torrent {} to {!r}".format(
            torrent[ "hash" ],
            torrent[ "location" ].as_posix()
        ) )


def add_torrents( torrents ):
    """
    """
    for torrent in torrents:
        log.debug( "Adding torrent to {!r} from {}".format(
            torrent[ "location" ].as_posix(),
            tuple( torrent[ "sources" ] )
        ) )


def execute_actions( actions ):
    """
    """
    remove_links     ( actions[ "links"    ][ "remove" ] )
    remove_torrents  ( actions[ "torrents" ][ "remove" ] )
    add_torrents     ( actions[ "torrents" ][ "add"    ] )
    resource_torrents( actions[ "torrents" ][ "source" ] )
    move_torrents    ( actions[ "torrents" ][ "move"   ] )
    add_links        ( actions[ "links"    ][ "add"    ] )
