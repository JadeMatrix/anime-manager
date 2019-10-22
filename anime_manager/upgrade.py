import logging


log = logging.getLogger( __name__ )


def flatdb_v5_to_v6( server, flatdb, db ):
    """Completely rewrite a flat database to upgrade from version 5 to 6
    
    Modifies the flat database in-place
    
    Args:
        server (torrents.TransmissionServer):
                        The Transmission server to use as a reference
        flatdb (dict):  A flat database to normalize in-place
        db (dict):      Newly loaded full database as fallback reference
    """
    
    # Modules specific to v6 cache upgrade
    import anime_manager.database
    import anime_manager.filesystem
    import os.path
    import pathlib
    import re
    
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
                raise anime_manager.database.InvalidDatabaseError(
                    "{!r} is not a file in torrent {}".format(
                        ( dest / source ).as_posix(),
                        hash
                    )
                )
            links.append( ( dest, {
                "torrent" : torrents[ hash ],
                "file"    : file,
                "dest"    : dest,
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
    parse_episode = re.compile(
        r"( - (s(\d+)e?)?((\d+)|\s*(\S.*))?)?(\.[a-zA-Z][a-zA-Z0-9]+)+$"
    )
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
        "torrents"    : torrents,
        "directories" : directories,
    } )
