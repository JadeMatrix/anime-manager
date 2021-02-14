import anime_manager.torrents
import anime_manager.library

import logging
import os.path
import pathlib
import re
import verboselogs

import yaml


log = verboselogs.VerboseLogger( __name__ )

hash_regex = r"[0-9a-fA-F]{40}"

# Used for flatdb normalization
placeholder_pattern = re.compile( r"\$NAME:(" + hash_regex + r")\$" )


class InvalidDatabaseError( Exception ):
    def __init__( self, reason ):
        Exception.__init__(
            self,
            "invalid database: {}".format( reason )
        )


def empty_flatdb():
    """Get an empty flat database
    
    Returns:
        dict
    """
    
    return {}


def normalize( db ):
    """Normalize a full database, adding missing optional/implicit fields
    
    Args:
        db (dict):  A full database
    
    Returns:
        dict:   A full(er) database
    
    Raises:
        InvalidDatabaseError:   A field is malformed or is missing and could not
                                be resolved
    """
    
    for field in (
        "directories",
        "shows",
        "torrents",
    ):
        if field not in db:
            raise InvalidDatabaseError( "missing required field {!r}".format(
                field
            ) )
    
    # Normalize directories ####################################################
    
    db[ "directories" ][ "media" ] = pathlib.Path(
        db[ "directories" ][ "media" ] if "media" in db[ "directories" ]
        else "."
    )
    
    for field in (
        ( "trash"      , ".Trash"     , ),
        ( "torrents"   , ".Torrents"  , ),
        ( "in progress", "In Progress", ),
        ( "archived"   , "Archived"   , ),
        ( "rainy day"  , "Rainy Day"  , ),
    ):
        if field[ 0 ] in db[ "directories" ]:
            directory = pathlib.Path( db[ "directories" ][ field[ 0 ] ]  )
        else:
            directory = pathlib.Path( field[ 1 ] )
        if not directory.is_absolute():
            # Doesn't matter if media directory is absolute or not
            directory = db[ "directories" ][ "media" ] / directory
        db[ "directories" ][ field[ 0 ] ] = directory
    
    # Normalize torrents & shows ###############################################
    
    if not isinstance( db[ "torrents" ], dict ):
        raise InvalidDatabaseError( "torrents list must be a dictionary" )
    
    for torrent_hash, torrent_config in db[ "torrents" ].items():
        if not re.match(
            r"^{}$".format( hash_regex ),
            torrent_hash
        ):
            raise InvalidDatabaseError(
                "torrent ID {!r} is not a valid hash".format( torrent_hash )
            )
        
        if "source" in torrent_config:
            torrent_config[ "source" ] = str( torrent_config[ "source" ] )
        else:
            raise InvalidDatabaseError(
                "torrent ID {!r} missing required key 'source'".format(
                    torrent_hash
                )
            )
        
        if "location" in torrent_config:
            try:
                torrent_config[ "location" ] = pathlib.Path(
                    torrent_config[ "location" ]
                )
            except TypeError:
                raise InvalidDatabaseError(
                    "torrent ID {!r} manual 'location' not a path".format(
                        torrent_hash
                    )
                )
        
        if "episodes" not in torrent_config:
            raise InvalidDatabaseError(
                "torrent ID {!r} missing required key 'episodes'".format(
                    torrent_hash,
                )
            )
        elif not isinstance( torrent_config[ "episodes" ], list ):
            raise InvalidDatabaseError(
                "torrent ID {!r} episode list is not a list".format(
                    torrent_hash
                )
            )
        
        for episode in torrent_config[ "episodes" ]:
            if "pattern" in episode:
                if "regex" not in episode[ "pattern" ]:
                    raise InvalidDatabaseError(
                        (
                            "torrent ID {!r} specifies pattern with no 'regex' "
                            "field"
                        ).format(
                            torrent_hash,
                        )
                    )
                else:
                    try:
                        episode[ "pattern" ][ "regex" ] = re.compile(
                            episode[ "pattern" ][ "regex" ]
                        )
                    except re.error as ree:
                        raise InvalidDatabaseError( (
                            "invalid episode regex for torrent ID {!r}: {!r}"
                        ).format( torrent_hash, ree ) )
                
                # TODO: Validation & normalization
                continue
            
            if "episode" not in episode:
                episode[ "episode" ] = 1
            
            if "season" in episode:
                try:
                    episode[ "season" ] = int( episode[ "season" ] )
                except ( ValueError, TypeError ) as e:
                    raise InvalidDatabaseError( (
                        "invalid season number for torrent ID {!r}: {!r}"
                    ).format( torrent_hash, e ) )
            else:
                episode[ "season" ] = 1
            
            for field in (
                "title",
                "seasons",
            ):
                if field not in episode[ "show" ]:
                    raise InvalidDatabaseError( (
                        "show for torrent ID {!r} missing required key {!r}"
                    ).format( torrent_hash, field ) )
            
            if len( episode[ "show" ][ "seasons" ] ) < 1:
                raise InvalidDatabaseError( (
                    "show for torrent ID {!r} needs at least one season"
                ).format( torrent_hash ) )
            
            for season in episode[ "show" ][ "seasons" ]:
                for field in (
                    "year",
                    "season",
                ):
                    if field not in season:
                        raise InvalidDatabaseError( (
                            "season for show for torrent ID {!r} missing "
                            "required key {!r}"
                        ).format( torrent_hash, field ) )
                try:
                    season[ "year" ] = int( season[ "year" ] )
                except ( ValueError, TypeError ) as e:
                    raise InvalidDatabaseError( (
                        "invalid year for season for show for torrent  ID "
                        "{!r}: {!r}"
                    ).format( torrent_hash, e ) )
                
                sqm = anime_manager.library.season_quarter_map
                if season[ "season" ] not in sqm:
                    raise InvalidDatabaseError( (
                        "yearly season for season for show for torrent ID {!r} "
                        "not one of {}"
                    ).format(
                        torrent_hash,
                        tuple( sqm.keys() )
                    ) )
                
                if "episodes" in season:
                    try:
                        season[ "episodes" ] = int( season[ "episodes" ] )
                    except ( ValueError, TypeError ) as e:
                        raise InvalidDatabaseError( (
                            "invalid episode count for season for show for "
                            "torrent ID {!r}: {!r}"
                        ).format( torrent_hash, e ) )
    
    return db


def normalize_flatdb( server, flatdb ):
    """Normalize a flat database to the current spec
    
    Important for manager version upgrades; essentially a no-op if the format
    has not changed.  Only flat database format changes that effect the logic
    of the rest of the utility are handled here; that is, anything an silent
    library rebuild won't fix.
    
    Args:
        server (torrents.TransmissionServer):
                        The Transmission server to use as a reference
        flatdb (dict):  A flat database to normalize in-place
    """
    
    for hash, entry in flatdb.items():
        # Field "archived" added 09/03/2019 ####################################
        if "archived" not in entry:
            entry[ "archived" ] = False
        
        # Placeholder paths replaced with full paths 10/12/2019 ################
        if "files" not in entry:
            entry[ "files" ] = {}
        # Copy of keys iterable as we may be modifying the dictionary
        dests = tuple( entry[ "files" ].keys() )
        
        for dest in dests:
            # Look for & replace placeholder filenames
            new_source = []
            for part in entry[ "files" ][ dest ].parts:
                match = placeholder_pattern.match( part )
                if match:
                    hash = match.group( 1 )
                    new_source.append(
                        server.torrent_names( ( hash, ) )[ hash ]
                    )
                else:
                    new_source.append( part )
            source = pathlib.Path( *new_source )
            
            if dest.suffix == ".$EXTENSION$":
                del entry[ "files" ][ dest ]
                dest = dest.with_suffix( source.suffix )
            entry[ "files" ][ dest ] = source
        
        # Torrent source history removed 10/12/2019 ############################
        if "sources" in entry:
            source = tuple( entry[ "sources" ] )[ -1 ]
            entry[ "source" ] = source
        
        # Preservation of relative symlinks in cache added 10/14/2019 ##########
        files = {}
        for dest, source in entry[ "files" ].items():
            if dest.is_absolute() and source .is_absolute():
                d, s = anime_manager.library.relative_link_pair( dest, source )
                files[ d ] = s
            else:
                files[ dest ] = source
        entry[ "files" ] = files
        
        # Field "archived" changed to more generic "status" 01/20/2020 #########
        if "archived" in entry:
            archived = entry[ "archived" ]
            del entry[ "archived" ]
        else:
            archived = False
        if "status" not in entry:
            # Set all non-stopped entries to "checking" in case they haven't
            # finished checking; they should be updated during library update
            entry[ "status" ] = "stopped" if archived else "checking"
