import logging
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
name_placeholder = "$NAME$"


class InvalidDatabaseError( Exception ):
    def __init__( self, reason ):
        Exception.__init__(
            self,
            "invalid database: {}".format( reason )
        )


def year_quarter_for_torrent( db, hash ):
    """
    
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
    
    return "%(year)s%(quarter)s" % {
        "year"    : min_torrent_year,
        "quarter" : min_torrent_quarter,
    }


def show_link_for_episode( db, episode ):
    """
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


def placeholder_filename( location, file ):
    """
    """
    return location / name_placeholder / file


def empty_database():
    """Return an empty database structure
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
    """
    
    """
    
    return {}


def normalize( db ):
    """
    
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
    
    if "media" in db[ "directories" ]:
        db[ "directories" ][ "media" ] = pathlib.Path(
            db[ "directories" ][ "media" ]
        )
    
    for field in (
        ( "trash"      , ".Trash"     , ),
        ( "torrents"   , ".Torrents"  , ),
        ( "in progress", "In Progress", ),
        ( "archived"   , "Archived"   , ),
        ( "rainy day"  , "Rainy Day"  , ),
    ):
        if field[ 0 ] in db[ "directories" ]:
            db[ "directories" ][ field[ 0 ] ] = pathlib.Path(
                db[ "directories" ][ field[ 0 ] ]
            )
        elif "media" in db[ "directories" ]:
            db[ "directories" ][ field[ 0 ] ] = (
                db[ "directories" ][ "media" ] / field[ 1 ]
            )
        else:
            raise InvalidDatabaseError( (
                "missing required field [{0!r}][{1!r}] and no fallback "
                "base [{0!r}][{2!r}]"
            ).format(
                "directories",
                field[ 0 ],
                "media"
            ) )
    
    # Normalize torrents & shows ###############################################
    
    if not isinstance( db[ "torrents" ], dict ):
        raise InvalidDatabaseError( "torrents list must be a dictionary" )
    
    for torrent_hash, torrent_config in db[ "torrents" ].items():
        if not re.match(
            r"^[0-9a-f]{40}$",
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
    """
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
            ] = filename
    
    return flatdb


def diff( old, new ):
    """
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
            actions[ "links" ][ "add" ].append( {
                "source" : placeholder_filename(
                    new[ hash ][ "location" ],
                    source
                ),
                "dest"   : dest
            } )
    
    for hash in old_hashes - new_hashes:
        actions[ "torrents" ][ "remove" ].append( hash )
        for dest in new[ hash ][ "files" ].items():
            actions[ "links" ][ "remove" ].append( dest )
    
    for hash in new_hashes & old_hashes:
        new_sources = new[ hash ][ "sources" ] - old[ hash ][ "sources" ]
        if new_sources:
            actions[ "torrents" ][ "source" ].append( {
                "hash"    : hash,
                "sources" : new_sources
            } )
        
        if new[ hash ][ "location" ] != old[ hash ][ "location" ]:
            actions[ "torrents" ][ "move" ].append( {
                "hash"     : hash,
                "location" : new[ hash ][ "location" ]
            } )
        
        old_links = set( old[ hash ][ "files" ].keys() )
        new_links = set( new[ hash ][ "files" ].keys() )
        
        for link in new_links - old_links:
            actions[ "links" ][ "add" ].append( {
                "source" : placeholder_filename(
                    new[ hash ][ "location" ],
                    new[ hash ][ "files" ][ link ]
                ),
                "dest"   : link
            } )
        
        for link in old_links - new_links:
            actions[ "links" ][ "remove" ].append( link )
        
        for link in old_links & new_links:
            if new[ hash ][ "files" ][ link ] != old[ hash ][ "files" ][ link ]:
                actions[ "links" ][ "remove" ].append( link )
                actions[ "links" ][ "add" ].append( {
                    "source" : placeholder_filename(
                        new[ hash ][ "location" ],
                        new[ hash ][ "files" ][ link ]
                    ),
                    "dest"   : link
                } )
    
    return actions

