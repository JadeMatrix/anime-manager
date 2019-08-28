import anime_manager.arguments
import anime_manager.database
import anime_manager.torrents

import logging
import os
import pathlib
import sys
import time

import watchdog.observers
import watchdog.events
import yaml


log = logging.getLogger( __name__ )


def configure_logging( args ):
    """Configure logging based on command-line arguments
    
    Args:
        args (iterable):    Command-line arguments (see `arguments` submodule)
    """
    
    logging.basicConfig(
        filename = (
            args.log_file if args.log_file is not None
            else args.cache_dir / "log"
        ),
        level = getattr( logging, args.log_level )
    )


def reload_database( args ):
    """Run a single database update
    
    Args:
        args (argparse.Namespace):  Command-line arguments (see `arguments`
                                    submodule)
    """
    
    args.cache_dir.mkdir( parents = True, exist_ok = True )
    
    cache_db = args.cache_dir / "flatdb_cache.yaml"
    
    # Load cached flat database
    try:
        with open( cache_db, encoding = "utf8" ) as old_db_file:
            old_flatdb = yaml.full_load( old_db_file )
            log.info( "loaded flat database cache" )
    except IOError:
        old_flatdb = anime_manager.database.empty_flatdb()
        log.info( "no flat database cache, creating" )
    
    # Load new database
    with open( args.database, encoding = "utf8" ) as db_file:
        new_db = anime_manager.database.normalize(
            yaml.full_load( db_file )
        )
        directories = new_db[ "directories" ]
        new_flatdb = anime_manager.database.flatten( new_db )
        del new_db
    
    # Make changes
    anime_manager.torrents.execute_actions(
        args.transmission,
        anime_manager.database.diff( old_flatdb, new_flatdb ),
        None if args.no_trash else directories[ "trash" ]
    )
    anime_manager.torrents.cleanup_empty_dirs( directories )
    
    # Save new database as cache
    with open( cache_db, "w" ) as new_db_file:
        yaml.dump( new_flatdb, new_db_file )
        log.info( "saved new flat database cache" )


class AutoManageTorrentsHandler( watchdog.events.FileSystemEventHandler ):
    
    def __init__( self, args ):
        watchdog.events.FileSystemEventHandler.__init__( self )
        self.args = args
        log.info( "checking database" )
        reload_database( self.args )
    
    def on_modified( self, event ):
        log.debug( "got event for {}".format( event.src_path ) )
        if pathlib.Path( event.src_path ) == self.args.database:
            log.info( "reloading database" )
            reload_database( self.args )


def run_update( argv = sys.argv[ 1 : ] ):
    """Run a single database update
    
    Args:
        argv (iterable):    Command-line arguments (see `arguments` submodule)
    """
    
    args = anime_manager.arguments.parser.parse_args( argv )
    configure_logging( args )
    reload_database( args )


def run_daemon( argv = sys.argv[ 1 : ] ):
    """Run an update daemon that watches for database changes
    
    Args:
        argv (iterable):    Command-line arguments (see `arguments` submodule)
    """
    
    args = anime_manager.arguments.parser.parse_args( argv )
    
    configure_logging( args )
    
    log.info( "starting" )
    
    observer = watchdog.observers.Observer()
    observer.schedule(
        AutoManageTorrentsHandler( args ),
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
