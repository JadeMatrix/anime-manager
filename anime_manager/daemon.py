import anime_manager.database
import anime_manager.torrents

import argparse
import logging
import os
import pathlib
import sys
import time

import watchdog.observers
import watchdog.events
import yaml


log = logging.getLogger( __name__ )


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
    
    def __init__( self, database, cache_dir, server ):
        watchdog.events.FileSystemEventHandler.__init__( self )
        self.database  = database
        self.cache_dir = cache_dir
        self.cache_db  = self.cache_dir / "flatdb_cache.yaml"
        self.server    = server
        log.info( "checking database" )
        self.reload_database()
    
    def reload_database( self ):
        # Load cached flat database
        try:
            with open( self.cache_db, encoding = "utf8" ) as old_db_file:
                old_flatdb = yaml.full_load( old_db_file )
                log.info( "loaded flat database cache" )
        except IOError:
            old_flatdb = anime_manager.database.empty_flatdb()
            log.info( "no flat database cache, creating" )
        
        # Load new database
        with open( self.database, encoding = "utf8" ) as db_file:
            new_db = anime_manager.database.normalize(
                yaml.full_load( db_file )
            )
            trash_directory = new_db[ "directories" ][ "trash" ]
            new_flatdb = anime_manager.database.flatten( new_db )
            del new_db
        
        # Make changes
        anime_manager.torrents.execute_actions(
            self.server,
            anime_manager.database.diff( old_flatdb, new_flatdb ),
            trash_directory
        )
        
        # Save new database as cache
        with open( self.cache_db, "w" ) as new_db_file:
            yaml.dump( new_flatdb, new_db_file )
            log.info( "saved new flat database cache" )
    
    def on_modified( self, event ):
        log.debug( "got event for {}".format( event.src_path ) )
        if pathlib.Path( event.src_path ) == self.database:
            log.info( "reloading database" )
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
    
    log.info( "starting" )
    
    observer = watchdog.observers.Observer()
    observer.schedule(
        AutoManageTorrentsHandler(
            args.database,
            args.cache_dir,
            args.transmission
        ),
        args.database.parent.as_posix()
    )
    observer.start()
    
    try:
        while True:
            time.sleep( 10 )
        
    except KeyboardInterrupt:
        log.info( "shutting down..." )
        observer.stop()
        observer.join()
        log.info( "exited cleanly" )
    
    except Exception as e:
        log.exception( "exception thrown while waiting for observer" )
        observer.stop()
        observer.join()
        exit( 1 )


if __name__ == "__main__":
    run()
