import anime_manager.database

import argparse
import logging
import os
import pathlib
import sys
import time
import watchdog.observers
import watchdog.events
import yaml


class AbsPathAction( argparse.Action ):
    """`argparse` action for converting strings to `pathlib.Path`s"""
    def __call__( self, parser, namespace, values, option_string = None ):
        try:
            values = pathlib.Path( values ).resolve()
        except TypeError:
            pass
        setattr( namespace, self.dest, values )

parser = argparse.ArgumentParser(
    description = "JadeMatrix's anime torrent manager"
)

parser.add_argument(
    "-d",
    "--database",
    metavar  = "FILENAME",
    action   = AbsPathAction,
    help     = "YAML torrent database file to watch for changes",
    required = True
)
parser.add_argument(
    "-t",
    "--transmission",
    metavar  = "ADDRESS:PORT",
    help     = "Transmission RPC server to use",
    required = True
)
parser.add_argument(
    "-c",
    "--cache-dir",
    metavar  = "DIRNAME",
    action   = AbsPathAction,
    help     = "persistent cache directory",
    required = True
)
parser.add_argument(
    "-g",
    "--log-file",
    metavar  = "FILENAME",
    action   = AbsPathAction,
    help     = "log file to use (defaults to 'log' in the cache directory",
    required = False
)
parser.add_argument(
    "-l",
    "--log-level",
    metavar  = "LEVEL",
    choices  = [
        "CRITICAL",
        "ERROR",
        "WARNING",
        "INFO",
        "DEBUG",
        "NOTSET",
    ],
    default  = "INFO",
    help     = "standard Python logging level to use",
    required = False
)


class AutoManageTorrentsHandler( watchdog.events.FileSystemEventHandler ):
    
    def __init__( self, database, cache_dir ):
        watchdog.events.FileSystemEventHandler.__init__( self )
        self.database  = database
        self.cache_dir = cache_dir
        self.reload_database()
    
    def reload_database( self ):
        # Load cached flat database
        try:
            with open( self.cache_dir / "database_cache.yaml" ) as old_db_file:
                old_flatdb = yaml.full_load( old_db_file )
                logging.info( "loaded flat database cache" )
        except IOError:
            old_flatdb = anime_manager.database.empty_flat_database()
            logging.info( "no flat database cache, creating" )
        
        # Load new database
        new_db = anime_manager.database.open_and_normalize( self.database )
        
        # 3-way diff (new/old/both) on torrent hashes
        (
            hashes_new,
            hashes_old,
            hashes_in_both,
        ) = anime_manager.database.torrent_hash_diff(
            new_db,
            old_flatdb
        )
        
        pass
        
        logging.info(
            "adding torrents: %s",
            hashes_new
        )
        logging.info(
            "removing torrents: %s",
            hashes_old
        )
        logging.info(
            "in-both torrents: %s",
            hashes_in_both
        )
    
    def on_modified( self, event ):
        logging.debug( "got event for " + str( event.src_path ) )
        if pathlib.Path( event.src_path ) == self.database:
            logging.info( "reloading database" )
            self.reload_database()


def run( argv = sys.argv[ 1 : ] ):
    args = parser.parse_args( argv )
    
    args.cache_dir.mkdir( parents = True, exist_ok = True )
    
    logging.basicConfig(
        filename = (
            args.log_file if args.log_file is not None
            else args.cache_dir / "log"
        ),
        level = getattr( logging, args.log_level )
    )
    
    """
    
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
    
    logging.info( "starting" )
    
    observer = watchdog.observers.Observer()
    observer.schedule(
        AutoManageTorrentsHandler(
            args.database,
            args.cache_dir,
        ),
        args.database.parent.as_posix()
    )
    observer.start()
    
    try:
        while True:
            time.sleep( 10 )
        
    except KeyboardInterrupt:
        logging.info( "shutting down..." )
        observer.stop()
        observer.join()
        logging.info( "exited cleanly" )
    
    except Exception as e:
        logging.exception( "exception thrown while waiting for observer" )
        observer.stop()
        observer.join()
        exit( 1 )


if __name__ == "__main__":
    run()
