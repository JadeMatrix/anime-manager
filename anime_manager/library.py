import anime_manager.filesystem
import anime_manager.torrents
import anime_manager.database

# import itertools
import logging
import pathlib
import re
import time


log = logging.getLogger( __name__ )


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
        quarter = anime_manager.database.season_quarter_map[
            season[ "season" ]
        ]
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
                        (relative to the appropriate status directory), with a
                        placehohlder extension to be replaced with the linked
                        episode file's
    """
    
    extension_placeholder = "$EXTENSION$"
    
    show = episode[ "show" ]
    multiseason = len( show[ "seasons" ] ) > 1
    season = show[ "seasons" ][ episode[ "season" ] - 1 ]
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
                extension_placeholder
            )
        else:
            link = link / "{}.{}".format(
                season_title,
                extension_placeholder
            )
    else:
        try:
            try:
                episode_string = "{:02d}".format( episode[ "episode" ] )
            except ValueError:
                episode_string = "{:f}".format( episode[ "episode" ] )
                whole, decimal = episode_string.strip( "0" ).split(
                    ".",
                    maxsplit = 1
                )
                episode_string = "{:02}.{}".format(
                    int( whole ),
                    decimal if decimal else 0
                )
            if multiseason and not has_season_title:
                episode_string = "e" + episode_string
        except ValueError:
            episode_string = " {}".format( episode[ "episode" ] )
        
        if multiseason and not has_season_title:
            link = link / "{} - s{}{}.{}".format(
                show[ "title" ],
                episode[ "season" ],
                episode_string,
                extension_placeholder
            )
        else:
            link = link / "{} - {}.{}".format(
                season_title,
                episode_string.strip(),
                extension_placeholder
            )
    
    return link


def update( server, cache, database, trash, dry_run = False ):
    """Run a library update
    
    Args:
        server (torrents.TransmissionServer):
                            The Transmission server to use as a reference
        cache (dict):       Cached flat database
        database (dict):    Newly loaded full database
        trash (pathlib.Path|None):
                            Trash directory (see `filesystem.trash_item()`)
        dry_run (bool):     Whether to skip actually executing actions
    
    Returns:
        tuple:  Two items:
            dict: The flatdb cache of the changes made based on the new database
            Exception|None: Any exception that was thrown while handling the new
                database; the flatdb cache will reflect the current state
    """
    
    old_hashes = set( cache.keys() )
    new_hashes = set( database[ "torrents" ].keys() )
    
    new_cache = anime_manager.database.empty_flatdb()
    
    stati = {}
    for status, shows in database[ "shows" ].items():
        for show in shows:
            stati[ show[ "title" ] ] = status
    
    try:
        # Clean up old links & torrents ########################################
        remove_hashes = old_hashes - new_hashes
        def iter_remove_links():
            for hash in remove_hashes:
                for dest in cache[ hash ][ "files" ].keys():
                    yield dest
        anime_manager.filesystem.remove_links( iter_remove_links(), trash, dry_run )
        server.remove_torrents( remove_hashes, trash, dry_run )
        
        # Check & modify remaining torrents & links ############################
        keep_hashes = old_hashes & new_hashes
        
        for hash in keep_hashes:
            new_cache[ hash ] = {
                "source"   : cache[ hash ][ "source"    ],
                "location" : cache[ hash ][ "location"  ],
                "archived" : cache[ hash ][ "archived"  ],
                "files"    : {}
            }
        
        # Move torrents
        torrents_source  = []
        torrents_move    = []
        torrents_archive = []
        for hash in keep_hashes:
            new_source = database[ "torrents" ][ hash ][ "source" ]
            if cache[ hash ][ "source" ] != new_source :
                torrents_source.append( {
                    "hash"   : hash,
                    "source" : new_source,
                } )
            
            download_to = (
                database[ "directories" ][ "torrents" ]
                / year_quarter_for_torrent( database, hash )
            )
            
            if download_to != cache[ hash ][ "location" ]:
                torrents_move.append( {
                    "hash"     : hash,
                    "location" : download_to,
                } )
            
            if cache[ hash ][ "archived" ] != database[ "torrents" ][ hash ][ "archived" ]:
                torrents_archive.append( {
                    "hash"    : hash,
                    "started" : not database[ "torrents" ][ hash ][ "archived" ],
                } )
        
        server.source_torrents( torrents_source, trash, dry_run )
        for torrent in torrents_source:
            new_cache[ torrent[ "hash" ] ][ "source" ] = torrent[ "source" ]
        
        server.move_torrents( torrents_move, trash, dry_run )
        for torrent in torrents_move:
            new_cache[ torrent[ "hash" ] ][ "location" ] = torrent[ "location" ]
        
        server.status_torrents( torrents_archive, trash, dry_run )
        for torrent in torrents_archive:
            new_cache[ torrent[ "hash" ] ][ "archived" ] = not torrent[ "started" ]
        
        torrent_names = {}
        get_names_tries = 0
        while True:
            try:
                torrent_names = server.torrent_names( keep_hashes )
                break
            except anime_manager.torrents.RPCError:
                if dry_run:
                    # Placeholders for dry run
                    torrent_names = dict(
                        ( h, "$HASH:{}$".format( h ) )
                        for h in keep_hashes
                    )
                    break
                elif get_names_tries < 5:
                    log.warning(
                        "not all torrent names available yet, retrying..."
                    )
                    get_names_tries -= 1
                    time.sleep( 1 )
                else:
                    raise
        
        for hash in keep_hashes:
            links_remove = []
            links_add    = {}
            
            files = {}
            for episode in database[ "torrents" ][ hash ][ "episodes" ]:
                dest = database[ "directories" ][
                    stati[ episode[ "show" ][ "title" ] ]
                ] / show_link_for_episode( database, episode )
                source = (
                    new_cache[ hash ][ "location" ]
                    / torrent_names[ hash ]
                )
                if "file" in episode:
                    source = source / episode[ "file" ]
                # Replace placeholder suffix with source's
                files[ dest.with_suffix( source.suffix ) ] = source
            
            new_dests = set( files )
            old_dests = set( cache[ hash ][ "files" ] )
            
            # Links that straight up don't exist anymore
            links_remove += old_dests - new_dests
            # Links that have changed what they point to
            for dest in old_dests & new_dests:
                if files[ dest ] != cache[ hash ][ "files" ][ dest ]:
                    links_remove.append( dest )
                    links_add[ dest ] = files[ dest ]
            anime_manager.filesystem.remove_links( links_remove, trash, dry_run )
            
            # Links to add
            for dest in new_dests - old_dests:
                links_add[ dest ] = files[ dest ]
            anime_manager.filesystem.add_links( links_add, trash, dry_run )
            
            new_cache[ hash ][ "files" ] = files
        
        # Add new torrents & links #############################################
        add_hashes = new_hashes - old_hashes
        
        # First add torrents...
        add_torrents = []
        for hash in add_hashes:
            download_to = (
                database[ "directories" ][ "torrents" ]
                / year_quarter_for_torrent( database, hash )
            )
            add_torrents.append( {
                "source"   : database[ "torrents" ][ hash ][ "source" ],
                "location" : download_to,
                "started"  : not database[ "torrents" ][ hash ][ "archived" ],
            } )
            new_cache[ hash ] = {
                "source"   : database[ "torrents" ][ hash ][ "source" ],
                "location" : download_to,
                "archived" : database[ "torrents" ][ hash ][ "archived" ],
            }
        server.add_torrents( add_torrents, trash, dry_run )
        
        # ... then add links once we can get torrent names
        torrent_names = {}
        get_names_tries = 0
        while True:
            try:
                torrent_names = server.torrent_names( add_hashes )
                break
            except anime_manager.torrents.RPCError:
                if dry_run:
                    # Placeholders for dry run
                    torrent_names = dict(
                        ( h, "$HASH:{}$".format( h ) )
                        for h in add_hashes
                    )
                    break
                elif get_names_tries < 5:
                    log.warning(
                        "not all torrent names available yet, retrying..."
                    )
                    get_names_tries -= 1
                    time.sleep( 1 )
                else:
                    raise
        
        for hash in add_hashes:
            links = {}
            for episode in database[ "torrents" ][ hash ][ "episodes" ]:
                dest = database[ "directories" ][
                    stati[ episode[ "show" ][ "title" ] ]
                ] / show_link_for_episode( database, episode )
                source = (
                    new_cache[ hash ][ "location" ]
                    / torrent_names[ hash ]
                )
                if "file" in episode:
                    source = source / episode[ "file" ]
                # Replace placeholder suffix with source's
                links[ dest.with_suffix( source.suffix ) ] = source
            anime_manager.filesystem.add_links( links, trash, dry_run )
            new_cache[ hash ][ "files" ] = links
    
    except Exception as e:
        log.error( "{}.{} thrown while updating, returning for re-raise".format(
            e.__class__.__module__,
            e.__class__.__name__
        ) )
        return new_cache, e
    else:
        return new_cache, None
