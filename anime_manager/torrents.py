import logging
import requests


def remove_links( links ):
    """
    """
    for link in links:
        logging.debug( "Removing link {!r}".format( link.as_posix() ) )


def add_links( links ):
    """
    """
    for link in links:
        logging.debug( "Adding link {!r} -> {!r}".format(
            link[ "source" ].as_posix(),
            link[ "dest" ].as_posix()
        ) )


def remove_torrents( torrents ):
    """
    """
    for torrent in torrents:
        logging.debug( "Removing torrent {}".format( torrent ) )


def resource_torrents( torrents ):
    """
    """
    for torrent in torrents:
        logging.debug( "Adding sources for torrent {!r} from {}".format(
            torrent[ "hash" ],
            tuple( torrent[ "sources" ] )
        ) )


def move_torrents( torrents ):
    """
    """
    for torrent in torrents:
        logging.debug( "Moving torrent {} to {!r}".format(
            torrent[ "hash" ],
            torrent[ "location" ].as_posix()
        ) )


def add_torrents( torrents ):
    """
    """
    for torrent in torrents:
        logging.debug( "Adding torrent to {!r} from {}".format(
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
