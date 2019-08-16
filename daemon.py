import argparse
import logging
import os
import yaml

# DEBUG:
import time

import anime_manager.utils
import anime_manager.database
import anime_manager.torrents


parser = argparse.ArgumentParser(
    description = "JadeMatrix's anime torrent manager"
)

parser.add_argument(
    "-d",
    "--database",
    help = "torrent database file to watch for changes",
    required = True
)
parser.add_argument(
    "-c",
    "--cache-dir",
    help = "persistent cache directory",
    required = True
)


def run():
    args = parser.parse_args()
    
    anime_manager.utils.mkdir_p( args.cache_dir )
    
    logging.basicConfig(
        filename = args.cache_dir + "/log",
        level    = logging.INFO
    )
    
    """
    
    X start libtorrent session
    - on startup & each time database changes:
        X load cached flat database
        X load new database
        X 3-way diff (new/old/both) on torrent hashes
        X remove old torrents from libtorrent session
        X move old torrent files to trash directory
        X remove old torrent symlinks (including any now-empty folders)
        - if startup:
            - add "both" torrents to session
        - add "new" torrents to session
        - wait for metadata for all torrents (this may take a while) -----------
        - generate flat database from new using metadata
        - flat diff (new/moved)
        - move moved symlinks
        - add new symlinks
        - write new flat database to cache
    
    """
    
    session = anime_manager.torrents.Session()
    
    logging.info( "libtorrent session started" )
    
    startup = True
    
    while True:
        
        # Load cached flat database
        try:
            with open( args.cache_dir + "/database_cache.yaml" ) as old_db_file:
                old_flatdb = yaml.load( old_db_file )
                logging.info( "loaded flat database cache" )
        except IOError:
            old_flatdb = anime_manager.database.empty_flat_database()
            logging.info( "no flat database cache, creating" )
        
        # Load new database
        new_db = anime_manager.database.open_and_normalize( args.database )
        
        # 3-way diff (new/old/both) on torrent hashes
        (
            hashes_new,
            hashes_old,
            hashes_in_both,
        ) = anime_manager.database.torrent_hash_diff(
            new_db,
            old_flatdb
        )
        
        # logging.info(
        #     "adding torrents: %s",
        #     hashes_new
        # )
        # logging.info(
        #     "removing torrents: %s",
        #     hashes_old
        # )
        # logging.info(
        #     "in-both torrents: %s",
        #     hashes_in_both
        # )
        
        logging.info(
            "removing %s torrents",
            len( hashes_old )
        )
        for hash in hashes_old:
            # Remove old torrents from libtorrent session
            if hash in session:
                del session[ hash ]
                logging.info(
                    "removed torrent %r from libtorrent session",
                    hash
                )
            
            # Move old torrent files to trash directory
            saved_to = old_flatdb[ hash ][ "saved to" ]
            try:
                trashed_to = anime_manager.torrents.trash( saved_to, new_db )
                logging.info(
                    "moved downloaded file %r to trash (%r)",
                    saved_to,
                    trashed_to
                )
            except OSError as e:
                logging.error(
                    "couldn't move %r to trash (%s), skipping",
                    saved_to,
                    e
                )
            
            # Remove old torrent symlinks (including any now-empty folders)
            for file in old_flatdb[ hash ][ "files" ]:
                try:
                    anime_manager.torrents.remove_symlink(
                        file[ "to" ],
                        new_db
                    )
                except OSError as e:
                    logging.error(
                        "couldn't remove symlink %r (%s), skipping",
                        file[ "to" ],
                        e
                    )
        
        # Add "new" torrents to session
        hashes_to_add = list( hashes_new )
        if startup:
            # Add "both" torrents to session
            hashes_to_add.extend( hashes_in_both )
            startup = False
        
        for hash in hashes_to_add:
            torrent_config = new_db[ "torrents" ][ hash ]
            
            year_quarter = anime_manager.database.year_quarter_for_torrent(
                hash,
                new_db
            )
            
            save_to = (
                new_db[ "directories" ][ "torrents" ]
                + "/"
                + year_quarter
                + "/"
            )
            
            logging.info(
                "saving torrent %r to %r",
                hash,
                save_to
            )
            
            session[ hash ] = ( torrent_config[ "source" ], save_to )
        
        unnamed_torrents = len( session )
        
        while unnamed_torrents > 0:
            unnamed_torrents = 0
            
            for hash in session:
                torrent_name = session[ hash ].name()
                if not len( torrent_name ):
                    unnamed_torrents += 1
                
            logging.info(
                "%s unnamed torrents",
                unnamed_torrents
            )
            
            time.sleep( 5 )
        
        logging.info( "all torrents named, writing resume files" )
        
        # asdf
        waiting_for = {}
        for hash in session:
            session[ hash ].save_resume_data()
            waiting_for[ hash ] = True
        
        # while len( waiting_for ):
        #     alerts = session.session.pop_alerts()
        #     for alert in alerts:
                
        
        
        while True:
            alerts = session.session.pop_alerts()
            # if len( alerts ):
            # if False:
            logging.info(
                "alerts since last pop:\n\t%s",
                "\n\t".join( alert.message() for alert in alerts )
            )
            # else:
            #     logging.info(
            #         "no alerts, current statuses:\n\t%s",
            #         "\n\t".join(
            #             "%s (%s): %.2f%% (%s)" % (
            #                 hash,
            #                 session[ hash ].name(),
            #                 session[ hash ].status().progress * 100,
            #                 (
            #                     anime_manager.torrents.libtorrent_state_strings[
            #                         session[ hash ].status().state
            #                     ] if session[ hash ].status().state < len(
            #                         anime_manager.torrents.libtorrent_state_strings
            #                     ) else "???"
            #                 )
            #             ) for hash in session
            #         )
            #     )
            #     # for hash in session:
            #     #     handle = session[ hash ]
            #     #     logging.info(
            #     #         "status for %r: %s",
            #     #         hash,
            #     #         anime_manager.torrents.libtorrent_state_strings[
            #     #             handle.status().state
            #     #         ]
            #     #     )
            time.sleep( 5 )
        
        break
    
    
    logging.info( "shutting down; this may take a while..." )
    
    # try:
    #     old_db = anime_manager.database.open_and_normalize(
    #         args.cache_dir + "/database_cache.yaml"
    #     )
    # except anime_manager.database.MissingDatabaseError:
    #     old_db = anime_manager.database.empty_database()
    
    # new_db = anime_manager.database.open_and_normalize( args.database )
    
    # new_torrent_list = anime_manager.database.torrent_list_from_db( new_db )
    # old_torrent_list = anime_manager.database.torrent_list_from_db( old_db )
    
    # (
    #     hashes_to_add,
    #     hashes_to_remove,
    #     hashes_to_move,
    # ) = anime_manager.database.torrent_diff(
    #     new_torrent_list,
    #     old_torrent_list
    # )
    
    # logging.info(
    #     "adding torrents: %s",
    #     hashes_to_add
    # )
    # logging.info(
    #     "removing torrents: %s",
    #     hashes_to_remove
    # )
    # logging.info(
    #     "moving torrents: %s",
    #     hashes_to_move
    # )
    
    # for hash in hashes_to_add:
    #     logging.info(
    #         "adding torrent %s : %s",
    #         hash,
    #         new_torrent_list[ hash ]
    #     )
    
    
    
    
    
    
    # session = anime_manager.torrents.Session()
    
    # for hash in new_torrents:
    #     session[ hash ] = (
    #         new_db[ "torrents" ][ hash ][ "source" ],
    #         (
    #             new_db[ "directories" ][ "torrents" ]
    #             + "/"
    #             + anime_manager.database.year_quarter_for_torrent( hash )
    #         ),
    #     )
    
    # logging.info(
    #     "removing torrents: %s",
    #     old_torrents
    # )


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        logging.info( "shutting down; this may take a while..." )
        pass
