"""JadeMatrix's anime torrent manager daemon"""


import watchdog.observers
import watchdog.events
import yaml

import argparse
import errno
import logging
import time
import os
import pathlib
import re
import shlex
import subprocess


################################################################################


parser = argparse.ArgumentParser(
    description = "JadeMatrix's anime torrent manager"
)

parser.add_argument(
    "-c",
    "--config",
    help = "torrent config/directory file to watch for changes",
    required = True
)
parser.add_argument(
    "-p",
    "--private-dir",
    help = "private cache directory, should probably not be /tmp",
    required = True
)
parser.add_argument(
    "-d",
    "--daemon",
    help = "address:port of the Deluge daemon to connect to",
    required = True
)


################################################################################


class InvalidConfigError( Exception ):
    def __init__( self, filename, reason ):
        Exception.__init__(
            self,
            "file %r is not a valid config: %s" % (
                filename,
                reason,
            )
        )


class DelugeExecFailed( Exception ):
    def __init__( self, command, output ):
        self.command = command
        self.output  = output
        Exception.__init__(
            self,
            "command failed: %r" % (
                command,
            )
        )


################################################################################


def seasons():
    return {
        "winter" : "q1",
        "spring" : "q2",
        "summer" : "q3",
        "fall"   : "q4"
    }


def mkdir_p( directory ):
    """Like `mkdir -p`, makes a directory and is a no-op if the directory exists
    
    Args:
        directory (str): The directory to make
    """
    
    try:
        os.makedirs( directory )
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise


def open_config( filename ):
    """Open & validate a config file
    
    Args:
        filename (str): The name of the YAML config file
    Returns:
        dict: A valid configuration object
    Raises:
        InvalidConfigError
    """
    
    with open( filename ) as f:
        config = yaml.load( f.read() )
    
    for field in (
        "media_directory",
        "torrent_directory",
        "torrents",
    ):
        if field not in config:
            raise InvalidConfigError(
                filename,
                "missing required field %r" % ( field, )
            )
    
    try:
        torrent_items = config[ "torrents" ].items()
    except AttributeError:
        raise InvalidConfigError(
            filename,
            "invalid torrents list"
        )
    
    for key, value in torrent_items:
        if not re.match(
            r"^[0-9a-f]{40}$",
            key
        ):
            raise InvalidConfigError(
                filename,
                "torrent ID %r is not a valid hash" % ( key, )
            )
        
        for field in (
            "source",
            "year",
            "season",
            "link_to",
        ):
            if field not in value:
                raise InvalidConfigError(
                    filename,
                    "torrent %r missing required field %r" % (
                        key,
                        field,
                    )
                )
        
        if value[ "season" ] not in seasons():
            raise InvalidConfigError(
                filename,
                "torrent %r has unrecognized season %r" % (
                    key,
                    value[ "season" ],
                )
            )
    
    return config


################################################################################


class AutoManageTorrentsHandler( watchdog.events.FileSystemEventHandler ):
    
    
    def __init__( self, daemon, username, password, private_dir ):
        self.daemon      = daemon
        self.username    = username
        self.password    = password
        self.private_dir = pathlib.PurePath( private_dir )
        
        self.media_directory   = None
        # self.torrent_directory = None
    
    
    def send_commands( self, *commands ):
        """Send a number of commands to a Deluge daemon
        
        Args:
            *commands (list[str]): A set of commands to send the daemon once
                connection has been established
        Returns:
            str: The string output of the commands, if successful
        Raises:
            DelugeExecFailed
        """
        
        result = subprocess.run(
            args = [
                "deluge-console",
                "-l",
                self.private_dir / "deluge_console_log"
                ";".join( (
                    "connect %s %s %s" % (
                        self.daemon,
                        self.username,
                        self.password,
                    ),
                    *commands
                ) )
            ],
            stdout = subprocess.PIPE,
            stderr = subprocess.PIPE
        )
        
        if result.returncode != 0:
            raise DelugeExecFailed(
                result.args,
                result.stderr
            )
        else:
            return result.stdout.decode( "utf-8" )
    
    
    def trash( self, item ):
        """
        
        """
        
        item_path = pathlib.PurePath( item )
        
        # Put data into a `.Trash/` directory
        trash_directory = self.media_directory / ".Trash"
        
        mkdir_p( trash_directory )
        
        append = 1
        trash_to = trash_directory / item_path.parts[ -1 ]
        
        while os.path.exists( trash_to ):
            trash_to = trash_directory / "%s-%s" % (
                item_path.parts[ -1 ],
                append
            )
            append += 1
        
        os.rename(
            item_path,
            trash_to
        )
        
        return trash_to
    
    
    def remove_torrents( self, **kwargs ):
        """
        
        """
        
        for hash, torrent in kwargs.items():
            
            logging.info(
                "removing torrent %s..." % ( hash, )
            )
            
            saved_to = self.media_directory / ".Torrents" / "%s%s" % (
                torrent[ "year" ],
                seasons()[ torrent[ "season" ] ],
            )
            
            output = self.send_commands(
                self.daemon,
                "info %s" % ( hash, )
            )
            
            torrent_name = re.search(
                r"Name: (.+)\nID: [0-9a-f]{40}",
                output,
                re.DOTALL
            ).group( 1 )
            
            # Remove torrent without deleting data
            self.send_commands(
                self.daemon,
                "rm %s" % ( hash, )
            )
            
            linked_to = pathlib.PurePath( torrent[ "link_to" ] ) / torrent_name
            
            if os.path.islink( linked_to ):
                os.remove( linked_to )
            else:
                link_trashed_to = self.trash( linked_to )
                logging.warning(
                    (
                        "expected %r to be a symlink, real file/directory "
                        "found; it has been moved to %r"
                    ),
                    str( linked_to       ),
                    str( link_trashed_to )
                )
            
            torrent_data = saved_to / torrent_name
            trashed_to = self.trash( torrent_data )
            
            logging.info(
                "removed torrent %s, its data has been moved to %s",
                hash,
                trashed_to
            )
    
    
    def add_torrents( self, **kwargs ):
        """
        
        """
        
        for hash, torrent in kwargs.items():
            
            save_to = self.media_directory / ".Torrents"
            
            # Ensure `.Torrents` directory exists
            mkdir_p( save_to )
            
            save_to = save_to / "%s%s" % (
                torrent[ "year" ],
                seasons()[ torrent[ "season" ] ],
            )
            
            output = self.send_commands(
                self.daemon,
                "add --path=%s %s" % (
                    shlex.quote( save_to             ),
                    shlex.quote( torrent[ "source" ] ),
                ),
                "info %s" % ( hash, )
            )
            
            torrent_name = re.search(
                r"Name: (.+)\nID: [0-9a-f]{40}",
                output,
                re.DOTALL
            ).group( 1 )
            
            link_to = pathlib.PurePath( torrent[ "link_to" ] )
            link_to_directory = link_to.parts[ : -1 ]
            
            # Ensure link parent directory exists
            mkdir_p( link_to_directory )
            
            # Create relative path from link location to original
            relative_src = [ ".." ] * len( link_to_directory )
            relative_src.append( save_to  )
            relative_src.append( torrent_name )
            
            os.symlink(
                pathlib.PurePath( *relative_src ),
                link_to
            )


    def modify_torrents( self, **kwargs ):
        """
        
        """
        
        pass
        
        # TODO: change of source
        # TODO: change of dowload location
        # TODO: change of link
    
    
    def on_modified( self, event ):
        
        logging.info( "reloading config..." )
        
        try:
            config = open_config( event.src_path )
        except InvalidConfigError as e:
            logging.error(
                "skipping reload: %s",
                e
            )
            return
        
        config_media_directory = pathlib.PurePath(
            config[ "media_directory" ]
        )
        
        current_version_filename = self.private_dir / "current_version.yaml"
        
        if os.path.isfile( current_version_filename ):
            try:
                current_version = open_config( event.src_path )
            except InvalidConfigError as e:
                logging.critical(
                    "cached config corrupt (%s), exiting!",
                    e
                )
                exit( 2 )
        else:
            current_version = {
                "media_directory"   : None,
                "torrents"          : {},
            }
        
        if self.media_directory is None:
            # This will happen on startup, use the cached config
            self.media_directory = pathlib.PurePath(
                current_version[ "media_directory" ]
            )
        
        if self.media_directory is None:
            # This will happen on first startup, no cached config
            self.media_directory = config_media_directory
            # Ensure media directory exists
            mkdir_p( self.media_directory )
        
        if self.media_directory != config_media_directory:
            # Media directory moved
            logging.info(
                (
                    "media directory moved from %r to %r, updating torrents & "
                    "links..."
                ),
                self.media_directory,
                config_media_directory
            )
            
            # TODO: do something with media_directory
            logging.warning(
                "media directory migration not yet supported, skipping"
            )
            config[ "media_directory" ] = str( self.media_directory )
            
            # logging.info(
            #     "Finished moving torrents & links"
            # )
        
        current_hashes = set( current_version[ "torrents" ] )
        config_hashes  = set(          config[ "torrents" ] )
        
        shared_hashes  = current_hashes.intersection( config_hashes  )
        missing_hashes = current_hashes.difference(   config_hashes  )
        new_hashes     =  config_hashes.difference(   current_hashes )
        
        # Remove missing hashes, delete symlinks
        if len( missing_hashes ):
            remove_torrents( **dict(
                (
                    key,
                    current_version[ "torrents" ][ key ]
                ) for key, value in missing_hashes
            ) )
        
        # Add new hashes, create symlinks
        if len( new_hashes ):
            add_torrents( **dict(
                (
                    key,
                    config[ "torrents" ][ key ]
                ) for key, value in new_hashes
            ) )
        
        # Check each same hash and change locations, move symlinks
        if len( shared_hashes ):
            modify_torrents( **dict(
                ( key, (
                    current_version[ "torrents" ][ key ],
                    config[          "torrents" ][ key ]
                ) ) for key in shared_hashes
            ) )
        
        # Write new file to current version
        with open( current_version_filename, "w" ) as f:
            f.write( yaml.dump( config ) )
        
        logging.info( "finished reloading config" )


################################################################################


if __name__ == "__main__":
    args = parser.parse_args()
    
    private_dir = pathlib.PurePath( args.private_dir )
    
    if not (
        os.path.exists( private_dir )
        and os.path.isdir( private_dir )
    ):
        mkdir_p( private_dir )
    
    logging.basicConfig(
        filename = private_dir / "log",
        level    = logging.INFO
    )
    
    logging.info(
        "starting manager for Deluge daemon %s",
        args.daemon
    )
    
    handler = AutoManageTorrentsHandler(
        args.daemon,
        args.username,
        args.password,
        private_dir
    )
    
    try:
        handler.send_commands()
        logging.info(
            "successfully pinged Deluge daemon running on %s",
            args.daemon
        )
    except DelugeExecFailed as e:
        logging.error(
            "no Deluge daemon appears to be running on %s, please try again",
            args.daemon
        )
        return
    
    observer = watchdog.observers.Observer()
    observer.schedule(
        handler,
        args.config
    )
    observer.start()
    
    try:
        time.sleep( 1 )
    
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
