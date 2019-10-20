import anime_manager.filesystem
import anime_manager.library
import anime_manager.torrents

import logging
import os.path
import pathlib
import re

import yaml


log = logging.getLogger( __name__ )

current_flatdb_version = 6
hash_regex = r"[0-9a-fA-F]{40}"

# Used for flatdb normalization
placeholder_pattern = re.compile( r"\$NAME:(" + hash_regex + r")\$" )


class InvalidDatabaseError( Exception ):
    def __init__( self, reason ):
        Exception.__init__(
            self,
            "invalid database: {}".format( reason )
        )


def empty_database():
    """Get an empty full database
    
    Returns:
        dict
    """
    
    return {
        "directories" : {
            "media"       : None,
            "torrents"    : None,
            "in progress" : None,
            "archived"    : None,
            "rainy day"   : None,
        },
        "shows" : {
            "in progress" : [],
            "archived"    : [],
            "rainy day"   : [],
        },
        "torrents" : {}
    }


def empty_flatdb():
    """Get an empty flat database
    
    Returns:
        dict
    """
    
    return {
        "version"     : current_flatdb_version,
        "shows"       : {},
        "links"       : {},
        "torrents"    : {},
        "directories" : {},
    }


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
        
        if "archived" not in torrent_config:
            torrent_config[ "archived" ] = False
        
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
                        ).format( torrent_hash, e ) )
                
                # TODO: Validation & normalization
                continue
            
            if "episode" not in episode:
                episode[ "episode" ] = 1
            
            if "season" in episode:
                try:
                    episode[ "season" ] = int( episode[ "season" ] )
                except ValueError as e:
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
                except ValueError as e:
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
                    except ValueError as e:
                        raise InvalidDatabaseError( (
                            "invalid episode count for season for show for "
                            "torrent ID {!r}: {!r}"
                        ).format( torrent_hash, e ) )
    
    return db


def upgrade_flatdb_v6( server, flatdb, db ):
    """Completely rewrite a flat database to upgrade to version 6
    
    Modifies the flat database in-place
    
    Args:
        server (torrents.TransmissionServer):
                        The Transmission server to use as a reference
        flatdb (dict):  A flat database to normalize in-place
        db (dict):      Newly loaded full database as fallback reference
    """
    
    log.info( "upgrading cache to version 6" )
    
    directories = db[ "directories" ]
    dir_status = dict(
        p[ : : -1 ]
        for p in directories.items()
        if p[ 0 ] not in ( "media", "torrents", "trash" )
    )
    
    torrents = {}
    links    = []
    torrent_seasons = {}
    for hash, entry in flatdb.items():
        torrents[ hash ] = {
            "hash"     : hash,
            "source"   : entry[ "source"   ],
            "location" : entry[ "location" ],
            "name"     : server.torrent_names( ( hash, ) )[ hash ],
            "archived" : entry[ "archived" ],
        }
        
        if hash not in torrent_seasons:
            torrent_seasons[ hash ] = set()
        torrent_seasons[ hash ].add( entry[ "location" ].name )
        
        torrent_files = server.torrent_files( ( hash, ) )[ hash ]
        
        for dest, source in entry[ "files" ].items():
            file = None
            for torrent_file in torrent_files:
                if anime_manager.filesystem.path_endswith(
                    source,
                    torrent_file
                ):
                    file = pathlib.Path( *torrent_file.parts[ 1 : ] )
            if file is None:
                raise InvalidDatabaseError(
                    "{!r} is not a file in torrent {}".format(
                        ( dest / source ).as_posix(),
                        hash
                    )
                )
            links.append( ( dest, {
                "torrent" : torrents[ hash ],
                "file"    : file,
            } ) )
    
    # Sanity check
    unique_links = set( p[ 0 ] for p in links )
    duplicate_count = len( links ) - len( unique_links )
    if duplicate_count != 0:
        log.warning( "{} duplicate links found".format( duplicate_count ) )
    links = dict( links )
    
    shows = {}
    
    # Regenerate directories, shows information
    parse_season  = re.compile( r"^Season (\d+)( - (.+))?" )
    parse_episode   = re.compile( r"( - (s(\d+)e?)?((\d+)|\s*(\S.*))?)?(\.[a-zA-Z][a-zA-Z0-9]+)+$" )
    for dest in links:
        status   = None
        show     = None
        rest     = dest
        ep_title = dest.name
        
        for dir in dir_status:
            try:
                common = pathlib.Path( os.path.commonpath( (
                    dir,
                    dest,
                ) ) )
            except ValueError:
                continue
            
            if common in dir_status:
                status = dir_status[ common ]
                rest   = pathlib.Path( os.path.relpath( dest, common ) )
                show   = rest.parts[ 0 ]
                break
        if status is None:
            log.warning( (
                "unable to rebuild status of episode {!r}, setting show to "
                "in progress"
            ).format( ep_title ) )
            status = "in progress"
        
        between = rest.parts[ 1 : -1 ]
        
        # show [ / alt ] [ / season ] / episode
        if len( between ) == 0:
            season = 1
            season_title = None
            alt = None
        elif len( between ) == 1:
            match = parse_season.match( between[ 0 ] )
            if match:
                season = int( match.group( 1 ) )
                season_title = match.group( 3 )
                alt = None
            else:
                season = 1
                season_title = None
                alt = between[ 0 ]
        else:
            if len( between ) > 2:
                log.warning( (
                    "too many elements in season path, ignoring these: {}"
                ).format( between[ 1 : -1 ] ) )
            
            alt = between[ 0 ]
            
            match = parse_season.match( between[ -1 ] )
            if match:
                season = int( match.group( 1 ) )
                season_title = match.group( 3 )
        
        episode_match = parse_episode.search( ep_title )
        
        if show is None:
            if episode_match.group( 1 ) is None:
                show = ep_title
            else:
                show = ep_title[ : -len( episode_match.group( 1 ) ) ]
        
        try:
            episode = int( episode_match.group( 5 ) )
        except ( ValueError, TypeError ):
            if episode_match.group( 6 ) is None or (
                season_title if season_title is not None
                else show
            ).endswith( episode_match.group( 6 ) ):
                # Special case for single-episode seasons with "-" in their name
                # e.g. a lot of OVAs
                episode = 1
            else:
                episode = episode_match.group( 6 )
        
        if season is None:
            try:
                season = int( episode_match.group( 3 ) )
            except ( ValueError, TypeError ):
                season = 1
        
        log.debug( (
            "regenerated episode info:"
            "\n  link    : {}"
            "\n  source  : {}"
            "\n  show    : {}"
            "\n  y/q     : {}"
            "\n  status  : {}"
            "\n  alt     : {}"
            "\n  season  : {} ({!r})"
            "\n  episode : {}"
        ).format(
            rest.as_posix(),
            (
                  links[ dest ][ "torrent" ][ "location" ]
                / links[ dest ][ "torrent" ][ "name" ]
                / links[ dest ][ "file" ]
            ).as_posix(),
            show,
            torrent_seasons[ links[ dest ][ "torrent" ][ "hash" ] ],
            status,
            alt,
            season,
            season_title,
            episode
        ) )
        
        if show not in shows:
            shows[ show ] = {
                "status" : set(),
                "alts"   : {},
            }
        shows[ show ][ "status" ].add( status )
        
        if alt not in shows[ show ][ "alts" ]:
            shows[ show ][ "alts" ][ alt ] = {}
        
        if season not in shows[ show ][ "alts" ][ alt ]:
            shows[ show ][ "alts" ][ alt ][ season ] = {
                "title"        : set(),
                "year quarter" : set(),
                "episodes"     : {},
            }
        if season_title is not None:
            shows[ show ][ "alts" ][ alt ][ season ][ "title" ].add(
                season_title
            )
        shows[ show ][ "alts" ][ alt ][ season ][ "year quarter" ] |= (
            torrent_seasons[ links[ dest ][ "torrent" ][ "hash" ] ]
        )
        
        if episode not in shows[ show ][ "alts" ][ alt ][ season ][ "episodes" ]:
            shows[ show ][ "alts" ][ alt ][ season ][ "episodes" ][ episode ] = []
        shows[ show ][ "alts" ][ alt ][ season ][ "episodes" ][ episode ].append( links[ dest ] )
    
    titles = set( shows.keys() )
    for title in titles:
        show = shows[ title ]
        
        if len( show[ "status" ] ) == 1:
            show[ "status" ] = show[ "status" ].pop()
        else:
            log.warning( (
                "{} statuses{} for show {!r}, setting to in "
                "progress"
            ).format(
                ( "multiple" if len( show[ "status" ] ) else "no" ),
                (
                    " {}".format( tuple( show[ "status" ] ) )
                    if len( show[ "status" ] )
                    else ""
                ),
                title
            ) )
            show[ "status" ] = "in progress"
        
        for alt, seasons in show[ "alts" ].items():
            for season, season_info in seasons.items():
                if len( season_info[ "title" ] ) == 1:
                    season_info[ "title" ] = season_info[ "title" ].pop()
                else:
                    if len( season_info[ "title" ] ) != 0:
                        log.warning( (
                            "multiple subtitles {} for show {!r} season {}, "
                            "using none"
                        ).format(
                            tuple( season_info[ "title" ] ),
                            title,
                            season
                        ) )
                    season_info[ "title" ] = None
                
                if len( season_info[ "year quarter" ] ) == 1:
                    season_info[ "year quarter" ] = season_info[ "year quarter" ].pop()
                elif len( season_info[ "year quarter" ] ) == 0:
                    log.warning(
                        (
                            "no year/quarter for show {!r} season {}, using "
                            "99999q9"
                        ).format(
                            title,
                            season
                        )
                    )
                    season_info[ "year quarter" ] = "99999q9"
                else:
                    oldest_year_quarter = sorted( list(
                        season_info[ "year quarter" ]
                    ) )[ 0 ]
                    log.warning(
                        (
                            "multiple year/quarters for show {!r} season {}, "
                            "using oldest ({})"
                        ).format(
                            title,
                            season,
                            oldest_year_quarter
                        )
                    )
                    season_info[ "year quarter" ] = oldest_year_quarter
                
                episodes = {}
                for episode, episode_links in season_info[ "episodes" ].items():
                    fallback_episode = 100000
                    
                    if len( episode_links ) == 1:
                        episodes[ episode ] = episode_links[ 0 ]
                    else:
                        if episode is None:
                            log.warning( (
                                "episodes for show {!r} season {} found with "
                                "no number, giving them high numbers"
                            ).format(
                                title,
                                season
                            ) )
                        elif len( episode_links ) > 1:
                            log.warning( (
                                "multiple episode {}s for show {!r} season {}, "
                                "giving them high numbers"
                            ).format(
                                episode,
                                title,
                                season
                            ) )
                        
                        for link in episode_links:
                            episodes[ fallback_episode ] = link
                            fallback_episode += 1
                season_info[ "episodes" ] = episodes
    
    for title, show in shows.items():
        log.info( (
            "regenerated show info:"
            "\n  title  : {!r}"
            "\n  status : {}"
            "\n  alts   :{}"
        ).format(
            title,
            show[ "status" ],
            "".join(
                "\n    {!r}{}".format(
                    alt,
                    "".join(
                        (
                            "\n      season {}"
                            "\n        title    : {!r}"
                            "\n        y/q      : {}"
                            "\n        episodes :{}"
                        ).format(
                            season,
                            show[ "alts" ][ alt ][ season ][ "title" ],
                            show[ "alts" ][ alt ][ season ][ "year quarter" ],
                            "".join(
                                (
                                    "\n          {}"
                                    "\n            torrent : {}"
                                    "\n            file    : {!r}"
                                ).format(
                                    episode,
                                    show[ "alts" ][ alt ][ season ][ "episodes" ][ episode ][ "torrent" ][ "hash" ],
                                    show[ "alts" ][ alt ][ season ][ "episodes" ][ episode ][ "file" ].as_posix()
                                ) for episode in show[ "alts" ][ alt ][ season ][ "episodes" ]
                            )
                        ) for season in show[ "alts" ][ alt ]
                    )
                ) for alt in show[ "alts" ]
            )
        ) )
    
    # Replace contents of incoming flatdb
    flatdb.clear()
    flatdb.update( {
        "version"     : 6,
        "shows"       : shows,
        "links"       : links,
        "torrents"    : torrents,
        "directories" : directories,
    } )


def normalize_flatdb( server, flatdb, db ):
    """Normalize a flat database to the current spec
    
    Important for manager version upgrades; essentially a no-op if the format
    has not changed.  Only flat database format changes that effect the logic
    of the rest of the utility are handled here; that is, anything an silent
    library rebuild won't fix.
    
    Args:
        server (torrents.TransmissionServer):
                        The Transmission server to use as a reference
        flatdb (dict):  A flat database to normalize in-place
        db (dict):      Newly loaded full database as fallback reference
    """
    
    # Flat database format versioning added 10/15/2019 #########################
    if "version" not in flatdb:
        for hash, entry in flatdb.items():
            # Field "archived" added 09/03/2019 ################################
            if "archived" not in entry:
                entry[ "archived" ] = False
            
            # Placeholder paths replaced with full paths 10/12/2019 ############
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
            
            # Torrent source history removed 10/12/2019 ########################
            if "sources" in entry:
                source = tuple( entry[ "sources" ] )[ -1 ]
                entry[ "source" ] = source
            
            # Preservation of relative symlinks in cache added 10/14/2019 ######
            files = {}
            for dest, source in entry[ "files" ].items():
                if dest.is_absolute() and source .is_absolute():
                    d, s = anime_manager.library.relative_link_pair(
                        dest,
                        source
                    )
                    files[ d ] = s
                else:
                    files[ dest ] = source
            entry[ "files" ] = files
            
        # Major format change introduced 10/15/2019 ########################
        upgrade_flatdb_v6( server, flatdb, db )
    
    elif flatdb[ "version" ] > current_flatdb_version:
        raise InvalidDatabaseError(
            "unsupported cache format version {}; current is {}".format(
                flatdb[ "version" ],
                current_flatdb_version
            )
        )

