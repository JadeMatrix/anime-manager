import libtorrent
import logging
import os

import pathlib

import utils


libtorrent_state_strings = (
    'queued',
    'checking',
    'downloading metadata',
    'downloading',
    'finished',
    'seeding',
    'allocating'
)


class Session:
    
    def __init__( self, ports = ( 6881, 6891 ) ):
        self.session = session = libtorrent.session()
        self.session.listen_on( *ports )
        self.torrents = {}
    
    def __getitem__( self, hash ):
        return self.torrents[ hash ]
    
    def __setitem__( self, hash, source_dest_pair ):
        self.torrents[ hash ] = self.session.add_torrent( {
            "url"          : source_dest_pair[ 0 ],
            "save_path"    : source_dest_pair[ 1 ],
            "storage_mode" : libtorrent.storage_mode_t.storage_mode_sparse
        } )
    
    def __contains__( self, hash ):
        return hash in self.torrents
    
    def __delitem__( self, hash ):
        self.session.remove_torrent( self.torrents[ hash ] )
        del self.torrents[ hash ]
    
    def __iter__( self ):
        return dict.__iter__( self.torrents )
    
    def __len__( self ):
        return len( self.torrents )


def trash( save_to, db ):
    """
    
    """
    
    item_path = pathlib.PurePath( save_to )
    
    utils.mkdir_p( db[ "directories" ][ "trash" ] )
    
    trash_directory = pathlib.PurePath( db[ "directories" ][ "trash" ] )
    trash_to = trash_directory / item_path.parts[ -1 ]
    
    append = 1
    
    while os.path.exists( trash_to.as_posix() ):
        trash_to = trash_directory / "%s-%s" % (
            item_path.parts[ -1 ],
            append
        )
        append += 1
    
    os.rename(
        item_path.as_posix(),
        trash_to.as_posix()
    )
    
    return trash_to.as_posix()


def remove_symlink( link_to, db ):
    """
    
    """
    
    if os.path.islink( link_to ):
        os.remove( link_to )
    else:
        trashed_to = trash( link_to, db )
        logging.warning(
            (
                "expected %r to be a symlink, real file/directory found; it has"
                " been moved to %r"
            ),
            link_to,
            trashed_to
        )
