import anime_manager.arguments
import anime_manager.database
import anime_manager.filesystem
import anime_manager.library
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
        level  = getattr( logging, args.log_level ),
        format = "[%(levelname)s][%(name)s][%(asctime)s] %(message)s"
    )


def reload_database( args ):
    """Run a single database update
    
    Args:
        args (argparse.Namespace):  Command-line arguments (see `arguments`
                                    submodule)
    """
    
    args.cache_dir.mkdir( parents = True, exist_ok = True )
    
    cache_db = args.cache_dir / "flatdb_cache.yaml"
    
    server = anime_manager.torrents.TransmissionServer( args.transmission )
    
    # Load new database
    with open( args.database, encoding = "utf8" ) as db_file:
        db = anime_manager.database.normalize( yaml.full_load( db_file ) )
    
    # Load cached flat database
    try:
        with open( cache_db, encoding = "utf8" ) as cache_file:
            cache = yaml.full_load( cache_file )
            log.info( "loaded flat database cache" )
    except IOError:
        cache = anime_manager.database.empty_flatdb()
        log.info( "no flat database cache, creating" )
    
    anime_manager.database.normalize_flatdb( server, cache, db )
    
    # DEBUG:
    import sys
    yaml.dump(
        anime_manager.torrents.filter_paths( cache ),
        sys.stdout
    )
    exit()
    
    exception = None
    
    try:
        # Make changes
        anime_manager.library.update(
            server,
            cache,
            db,
            None if args.no_trash else db[ "directories" ][ "trash" ],
            args.dry_run
        )
        anime_manager.filesystem.cleanup_empty_dirs(
            db[ "directories" ],
            args.dry_run
        )
    except Exception as e:
        exception = e
    
    
    # Save new database as cache
    if not args.dry_run:
        with open( cache_db, "w" ) as cache_file:
            yaml.dump( cache, cache_file )
            log.info( "saved new flat database cache" )
    
    # Finally, re-raise any exceptions thrown by update:
    if exception is not None:
        raise exception


class AutoManageTorrentsHandler( watchdog.events.FileSystemEventHandler ):
    
    def __init__( self, args ):
        self.args = args
        log.info( "checking database" )
        self.reload()
        if self.args.dry_run:
            exit( 0 )
        watchdog.events.FileSystemEventHandler.__init__( self )
    
    def on_modified( self, event ):
        if (
            pathlib.Path( event.src_path ) == self.args.database
            and event.event_type in (
                watchdog.events.EVENT_TYPE_CREATED,
                watchdog.events.EVENT_TYPE_MODIFIED,
            )
        ):
            log.debug( "got event for {}".format( event.src_path ) )
            log.info( "reloading database" )
            self.reload()
    
    def reload( self ):
        try:
            reload_database( self.args )
        except anime_manager.database.InvalidDatabaseError as e:
            log.exception( "invalid database, please correct and re-save" )
        except:
            log.exception( "an error occurred while reloading database" )


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
