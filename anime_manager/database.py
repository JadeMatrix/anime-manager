import re

import yaml


season_quarter_map = {
    "winter" : "q1",
    "spring" : "q2",
    "summer" : "q3",
    "fall"   : "q4"
}


class MissingDatabaseError( Exception ):
    def __init__( self, filename ):
        Exception.__init__(
            self,
            "unable to open database file %r" % ( filename, )
        )


class InvalidDatabaseError( Exception ):
    def __init__( self, filename, reason ):
        Exception.__init__(
            self,
            "file %r is not a valid database: %s" % (
                filename,
                reason,
            )
        )


def open_and_normalize( filename ):
    """
    
    """
    
    try:
        with open( filename ) as db_file:
            db = yaml.load( db_file )
    except IOError:
        raise MissingDatabaseError( filename )
    
    for field in (
        "directories",
        "shows",
        "torrents",
    ):
        if field not in db:
            raise InvalidDatabaseError(
                filename,
                "missing required field %r" % ( field, )
            )
    
    # Normalize directories ####################################################
    
    if "media" in db[ "directories" ]:
        db[ "directories" ][ "media" ] = str(
            db[ "directories" ][ "media" ]
        )
    else:
        raise InvalidDatabaseError(
            filename,
            "missing required field [%r][%r]" % ( "directories", "media", )
        )
    
    for field in (
        ( "trash"      , ".Trash"     , ),
        ( "torrents"   , ".Torrents"  , ),
        ( "in progress", "In Progress", ),
        ( "archived"   , "Archived"   , ),
        ( "rainy day"  , "Rainy Day"  , ),
    ):
        if field[ 0 ] not in db[ "directories" ]:
            db[ "directories" ][ field[ 0 ] ] = (
                db[ "directories" ][ "media" ] + "/" + field[ 1 ]
            )
        else:
            db[ "directories" ][ field[ 0 ] ] = str(
                db[ "directories" ][ field[ 0 ] ]
            )
    
    # Normalize torrents & shows ###############################################
    
    if not isinstance( db[ "torrents" ], dict ):
        raise InvalidDatabaseError(
            filename,
            "torrents list must be a dictionary"
        )
    
    for torrent_hash, torrent_config in db[ "torrents" ].items():
        if not re.match(
            r"^[0-9a-f]{40}$",
            torrent_hash
        ):
            raise InvalidDatabaseError(
                filename,
                "torrent ID %r is not a valid hash" % ( torrent_hash, )
            )
        
        if "source" in torrent_config:
            torrent_config[ "source" ] = str( torrent_config[ "source" ] )
        else:
            raise InvalidDatabaseError(
                filename,
                "torrent ID %r missing required key 'source'" % (
                    torrent_hash,
                )
            )
        
        if "episodes" in torrent_config:
            if not isinstance( torrent_config[ "episodes" ], list ):
                raise InvalidDatabaseError(
                    filename,
                    "torrent ID %r episode list is not a list" % (
                        torrent_hash,
                    )
                )
            
            for episode in torrent_config[ "episodes" ]:
                episode_num = 1
                season_num  = 1
                if "episode" in episode:
                    try:
                        episode_num = int( episode[ "episode" ] )
                    except ValueError as e:
                        raise InvalidDatabaseError(
                            filename,
                            "invalid episode number for torrent ID %r: %s" % (
                                torrent_hash,
                                e
                            )
                        )
                if "season" in episode:
                    try:
                        season_num = int( episode[ "season" ] )
                    except ValueError as e:
                        raise InvalidDatabaseError(
                            filename,
                            "invalid season number for torrent ID %r: %s" % (
                                torrent_hash,
                                e
                            )
                        )
                
                for field in (
                    "title",
                    "seasons",
                ):
                    if field not in episode[ "show" ]:
                        raise InvalidDatabaseError(
                            filename,
                            (
                                "show for torrent ID %r missing required key %r"
                            ) % ( torrent_hash, field )
                        )
                
                if len( episode[ "show" ][ "seasons" ] ) < 1:
                    raise InvalidDatabaseError(
                        filename,
                        (
                            "show for torrent ID %r needs at least one season "
                        ) % ( torrent_hash, )
                    )
                
                for season in episode[ "show" ][ "seasons" ]:
                    for field in (
                        "year",
                        "season",
                    ):
                        if field not in season:
                            raise InvalidDatabaseError(
                                filename,
                                (
                                    "season for show for torrent ID %r missing "
                                    "required key %r"
                                ) % ( torrent_hash, field )
                            )
                    try:
                        season[ "year" ] = int( season[ "year" ] )
                    except ValueError as e:
                        raise InvalidDatabaseError(
                            filename,
                            (
                                "invalid year for season for show for torrent "
                                "ID %r: %s"
                            ) % ( torrent_hash, e )
                        )
                    
                    if season[ "season" ] not in season_quarter_map:
                        raise InvalidDatabaseError(
                            filename,
                            (
                                "yearly season for season for show for torrent "
                                "ID %r not one of %s"
                            ) % ( torrent_hash, season_quarter_map.keys() )
                        )
                
                episode[ "episode" ] = episode_num
                episode[ "season"  ] = season_num
                
        else:
            raise InvalidDatabaseError(
                filename,
                "torrent ID %r missing required key 'episodes'" % (
                    torrent_hash,
                )
            )
        
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
        #         filename,
        #         (
        #             "torrent ID %r missing required key 'episode', 'episodes',"
        #             " or 'episode map'"
        #         ) % ( torrent_hash, )
        #     )
    
    return db


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


def empty_flat_database():
    """
    
    """
    
    return {}


def year_quarter_for_torrent( hash, db ):
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


# def torrent_list_from_db( db ):
    
#     torrent_list = {}
    
#     for torrent_hash, torrent_config in db[ "torrents" ].items():
#         torrent_list[ torrent_hash ] = {
#             "source"  : torrent_config[ "source" ],
#             "save to" : (
#                 db[ "directories" ][ "torrents" ]
#                 + "/"
#                 + year_quarter_for_torrent( torrent_hash, db )
#             ),
#         }
    
#     return torrent_list


def torrent_hash_diff( new_db, old_flatdb ):
    """
    
    Returns:
        3-tuple (new, old, moved)
    """
    
    new_set  = set( new_db[ "torrents" ].keys() )
    old_set  = set(           old_flatdb.keys() )
    
    return (
        tuple( new_set - old_set ),
        tuple( old_set - new_set ),
        # tuple( hash for hash in ( new_set & old_set ) if (
        #     new_db[ hash ][ "save to" ] != old_flatdb[ hash ][ "save to" ]
        # ) )
        tuple( new_set & old_set ),
    )
