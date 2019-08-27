import logging
import os.path
import pathlib
import re

import yaml


log = logging.getLogger( __name__ )


season_quarter_map = {
    "winter" : "q1",
    "spring" : "q2",
    "summer" : "q3",
    "fall"   : "q4"
}
hash_regex = r"[0-9a-fA-F]{40}"
name_placeholder = "$NAME:{}$"


class InvalidDatabaseError( Exception ):
    def __init__( self, reason ):
        Exception.__init__(
            self,
            "invalid database: {}".format( reason )
        )


def year_quarter_for_torrent( db, hash ):
    """Generate a standardized year-quarter subdirectory name for a torrent
    
    Args:
        db (dict):  A full, unflattened database
        hash (str): The torrent hash
    
    Returns:
        str:    A string such as "2016q1" where the year and quarter (season)
                are the first time a file in that torrent are linked as an
                episode
    """
    
    min_torrent_year    = 99999
    min_torrent_quarter = "q9"
    
    for episode in db[ "torrents" ][ hash ][ "episodes" ]:
        
        season = episode[ "show" ][ "seasons" ][ episode[ "season" ] - 1 ]
        
        if season[ "year" ] < min_torrent_year:
            min_torrent_year = season[ "year" ]
        quarter = season_quarter_map[ season[ "season" ] ]
        if quarter < min_torrent_quarter:
            min_torrent_quarter = quarter
    
    return "{}{}".format( min_torrent_year, min_torrent_quarter )


def show_link_for_episode( db, episode ):
    """Generate an appropriate path for an episode within a season within a show
    
    Args:
        db (dict):      A full, unflattened database
        episode (dict): The relevant episode database entry
    
    Returns:
        pathlib.Path:   The filename and path to which to symlink the episode
                        (relative to the appropriate status directory)
    """
    
    show = episode[ "show" ]
    multiseason = len( show[ "seasons" ] ) > 1
    season = show[ "seasons" ][ episode[ "season" ] - 1 ]
    extension = "mkv"
    has_season_title = "title" in season
    season_title = season[ "title" ] if has_season_title else show[ "title" ]
    
    link = pathlib.Path( show[ "title" ] )
    
    if "alt" in episode:
        link = link / episode[ "alt" ]
    
    if multiseason:
        if "title" in season:
            link = link / "Season {} - {}".format(
                episode[ "season" ],
                season [ "title"  ]
            )
        else:
            link = link / "Season {}".format( episode[ "season" ] )
    
    if "episodes" in season and season[ "episodes" ] == 1:
        if multiseason and not has_season_title:
            link = link / "{} - s{}.{}".format(
                show[ "title" ],
                episode[ "season" ],
                extension
            )
        else:
            link = link / "{}.{}".format( season_title, extension )
    else:
        if multiseason and not has_season_title:
            link = link / "{} - s{}e{:02}.{}".format(
                show[ "title" ],
                episode[ "season"  ],
                episode[ "episode" ],
                extension
            )
        else:
            link = link / "{} - {:02}.{}".format(
                season_title,
                episode[ "episode" ],
                extension
            )
    
    return link


def placeholder_filename( hash, location, file ):
    """Generate a placeholder path to a file in a torrent with no metadata yet
    
    See `torrents.replace_placeholder_filename()`
    
    Args:
        hash (str):                 The parent torrent's hash
        location (pathlib.Path):    The parent torrent's download location
        file (str|pathlib.Path):    The file in the torrent (or "." for the
                                    entire torrent)
    
    Returns:
        pathlib.Path:   A path that can have the torrent download name placed in
                        it later once metadata is available / download starts
    """
    return location / name_placeholder.format( hash ) / file


def relative_link_pair( source, dest ):
    """Create an 'add-link' action so that the source is relative, if possible
    
    Args:
        source (pathlib.Path):  The target of the symlink, as cached (fully
                                prefixed up to the media directory)
        dest (pathlib.Path):    The filename & path of the symlink (fully
                                prefixed up to the media directory)
    
    Returns:
        dict:   An 'add-link' action:
            {
                "source" : pathlib.Path,
                "dest"   : pathlib.Path,
            }
    """
    common_path = pathlib.Path( os.path.commonpath( ( source, dest ) ) )
    if common_path != common_path.root:
        source = pathlib.Path( os.path.relpath( source, dest.parent ) )
    return { "source" : source, "dest" : dest }


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
            episode_num = 1
            season_num  = 1
            if "episode" in episode:
                try:
                    episode_num = int( episode[ "episode" ] )
                except ValueError as e:
                    raise InvalidDatabaseError( (
                        "invalid episode number for torrent ID {!r}: {!r}"
                    ).format( torrent_hash, e ) )
            if "season" in episode:
                try:
                    season_num = int( episode[ "season" ] )
                except ValueError as e:
                    raise InvalidDatabaseError( (
                        "invalid season number for torrent ID {!r}: {!r}"
                    ).format( torrent_hash, e ) )
            
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
                
                if season[ "season" ] not in season_quarter_map:
                    raise InvalidDatabaseError( (
                        "yearly season for season for show for torrent ID {!r} "
                        "not one of {}"
                    ).format(
                        torrent_hash,
                        tuple( season_quarter_map.keys() )
                    ) )
                
                if "episodes" in season:
                    try:
                        season[ "episodes" ] = int( season[ "episodes" ] )
                    except ValueError as e:
                        raise InvalidDatabaseError( (
                            "invalid episode count for season for show for "
                            "torrent ID {!r}: {!r}"
                        ).format( torrent_hash, e ) )
            
            episode[ "episode" ] = episode_num
            episode[ "season"  ] = season_num
        
        # episodes = []
        # if "episodes" in torrent_config:
        #     pass
        #     del torrent_config[ "episodes" ]
        #     torrent_config[ "episodes" ] = episodes
        # elif "episode" in torrent_config:
        #     pass
        #     del torrent_config[ "episode" ]
        #     torrent_config[ "episodes" ] = episodes
        # # elif "episode map" in torrent_config:
        # #     pass
        # else:
        #     raise InvalidDatabaseError(
        #         (
        #             "torrent ID %r missing required key 'episode', 'episodes',"
        #             " or 'episode map'"
        #         ) % ( torrent_hash, )
        #     )
    
    return db


def flatten( db ):
    """Turn a full database into a form suitable for caching (flat database)
    
    Args:
        db (dict):  A full database
    
    Returns:
        dict:   A flat database
    """
    
    flatdb = empty_flatdb()
    
    stati = {}
    for status, shows in db[ "shows" ].items():
        for show in shows:
            stati[ show[ "title" ] ] = status
    
    for hash, torrent in db[ "torrents" ].items():
        flatdb[ hash ] = {
            "sources"  : set( [ torrent[ "source" ] ] ),
            "location" : (
                db[ "directories" ][ "torrents" ]
                / year_quarter_for_torrent( db, hash )
            ),
            "files"    : {}
        }
        for episode in torrent[ "episodes" ]:
            if "file" in episode:
                filename = episode[ "file" ]
            else:
                filename = pathlib.Path()
            
            flatdb[ hash ][ "files" ][
                db[ "directories" ][ stati[ episode[ "show" ][ "title" ] ] ]
                / show_link_for_episode( db, episode )
            ] = (
                flatdb[ hash ][ "location" ]
                / name_placeholder.format( hash )
                / filename
            )
    
    return flatdb


def diff( old, new ):
    """Diff two flat databases by generating a set of actions to perform
    
    Args:
        old (dict): Previous flat database
        new (dict): Replacement flat database
    
    Returns:
        dict:   A set of actions in the form:
            {
                "links" : {
                    "remove" : [ pathlib.Path, ... ],
                    "add"    : [
                        { "source" : pathlib.Path, "dest" : pathlib.Path, },
                        ...
                    ],
                },
                "torrents" : {
                    "remove" : [ hash (str), ... ],
                    "source" : [
                        { "hash" : str, "sources" : set[str], },
                        ...
                    ],
                    "move"   : [
                        { "hash" : str, "location" : pathlib.Path },
                        ...
                    ],
                    "add"    : [
                        { "source" : str, "location" : pathlib.Path, },
                        ...
                    ],
                },
            }
    """
    
    old_hashes = set( old.keys() )
    new_hashes = set( new.keys() )
    
    actions = {
        "links" : {
            "remove" : [],
            "add"    : [],
        },
        "torrents" : {
            "remove" : [],
            "source" : [],
            "move"   : [],
            "add"    : [],
        },
    }
    
    for hash in new_hashes - old_hashes:
        actions[ "torrents" ][ "add" ].append( {
            "sources"  : new[ hash ][ "sources"  ],
            "location" : new[ hash ][ "location" ],
        } )
        for dest, source in new[ hash ][ "files" ].items():
            actions[ "links" ][ "add" ].append( relative_link_pair(
                placeholder_filename(
                    hash,
                    new[ hash ][ "location" ],
                    source
                ),
                dest
            ) )
    
    for hash in old_hashes - new_hashes:
        actions[ "torrents" ][ "remove" ].append( hash )
        for dest in old[ hash ][ "files" ].keys():
            actions[ "links" ][ "remove" ].append( dest )
    
    for hash in new_hashes & old_hashes:
        new_sources = new[ hash ][ "sources" ] - old[ hash ][ "sources" ]
        if new_sources:
            actions[ "torrents" ][ "source" ].append( {
                "hash"    : hash,
                "sources" : new_sources,
            } )
        
        if new[ hash ][ "location" ] != old[ hash ][ "location" ]:
            actions[ "torrents" ][ "move" ].append( {
                "hash"     : hash,
                "location" : new[ hash ][ "location" ],
            } )
        
        old_links = set( old[ hash ][ "files" ].keys() )
        new_links = set( new[ hash ][ "files" ].keys() )
        
        for link in new_links - old_links:
            actions[ "links" ][ "add" ].append( relative_link_pair(
                placeholder_filename(
                    hash,
                    new[ hash ][ "location" ],
                    new[ hash ][ "files" ][ link ]
                ),
                link
            ) )
        
        for link in old_links - new_links:
            actions[ "links" ][ "remove" ].append( link )
        
        for link in old_links & new_links:
            if new[ hash ][ "files" ][ link ] != old[ hash ][ "files" ][ link ]:
                actions[ "links" ][ "remove" ].append( link )
                actions[ "links" ][ "add" ].append( relative_link_pair(
                    placeholder_filename(
                        hash,
                        new[ hash ][ "location" ],
                        new[ hash ][ "files" ][ link ]
                    ),
                    link
                ) )
    
    return actions

