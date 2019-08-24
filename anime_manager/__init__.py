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


class AutoManageTorrentsHandler( watchdog.events.FileSystemEventHandler ):
    
    def __init__( self, database, cache_dir, server, no_trash ):
        watchdog.events.FileSystemEventHandler.__init__( self )
        self.database  = database
        self.cache_dir = cache_dir
        self.cache_db  = self.cache_dir / "flatdb_cache.yaml"
        self.server    = server
        self.no_trash  = no_trash
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
            trash_directory = (
                None if self.no_trash
                else new_db[ "directories" ][ "trash" ]
            )
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
    args = anime_manager.arguments.parser.parse_args( argv )
    
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
            args.transmission,
            args.no_trash
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
