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
        self.cache_db  = self.cache_dir / "flatdb_cache.yaml"
        self.reload_database()
    
    def reload_database( self ):
        # Load cached flat database
        try:
            with open( self.cache_db ) as old_db_file:
                old_flatdb = yaml.full_load( old_db_file )
                logging.info( "loaded flat database cache" )
        except IOError:
            old_flatdb = anime_manager.database.empty_flatdb()
            logging.info( "no flat database cache, creating" )
        
        # Load new database
        with open( self.database ) as db_file:
            new_flatdb = anime_manager.database.flatten(
                anime_manager.database.normalize(
                    yaml.full_load( db_file )
                )
            )
        
        # DEBUG:
        print( yaml.dump( new_flatdb ) )
        actions = anime_manager.database.diff( old_flatdb, new_flatdb )
        for remove_link in actions[ "links" ][ "remove" ]:
            print( "Removing link {!r}".format( remove_link.as_posix() ) )
        for remove_torrent in actions[ "torrents" ][ "remove" ]:
            print( "Removing torrent {}".format( remove_torrent ) )
        for add_torrent in actions[ "torrents" ][ "add" ]:
            print( "Adding torrent to {!r} from {}".format(
                add_torrent[ "location" ].as_posix(),
                tuple( add_torrent[ "sources" ] )
            ) )
        for source_torrent in actions[ "torrents" ][ "source" ]:
            print( "Adding sources for torrent {!r} from {}".format(
                source_torrent[ "hash" ],
                tuple( source_torrent[ "sources" ] )
            ) )
        for move_torrent in actions[ "torrents" ][ "move" ]:
            print( "Moving torrent {} to {!r}".format(
                move_torrent[ "hash" ],
                move_torrent[ "location" ].as_posix()
            ) )
        for add_link in actions[ "links" ][ "add" ]:
            print( "Adding link {!r} -> {!r}".format(
                add_link[ "source" ].as_posix(),
                add_link[ "dest" ].as_posix()
            ) )
        
        # Save new database as cache
        with open( self.cache_db, "w" ) as new_db_file:
            yaml.dump( new_flatdb, new_db_file )
            logging.info( "saved new flat database cache" )
    
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
