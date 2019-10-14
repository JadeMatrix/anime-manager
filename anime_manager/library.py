import anime_manager.filesystem
import anime_manager.torrents
import anime_manager.database

import logging
import os.path
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


def relative_link_pair( source, dest ):
    """Modify a source & destination so that the source is relative, if possible
    
    Args:
        source (pathlib.Path):  The target of the symlink, as cached (fully
                                prefixed up to the media directory)
        dest (pathlib.Path):    The filename & path of the symlink (fully
                                prefixed up to the media directory)
    
    Returns:
        tuple:  The potentially modified source & destination
    """
    
    common_path = pathlib.Path( os.path.commonpath( ( source, dest ) ) )
    if common_path != common_path.root:
        source = pathlib.Path( os.path.relpath( source, dest.parent ) )
    return source, dest


def update( server, cache, db, trash, dry_run = False ):
    """Run a library update
    
    Args:
        server (torrents.TransmissionServer):
                            The Transmission server to use as a reference
        cache (dict):       Cached flat database, updated in-place
        db (dict):          Newly loaded full database
        trash (pathlib.Path|None):
                            Trash directory (see `filesystem.trash_item()`)
        dry_run (bool):     Whether to skip actually executing actions
    """
    
    # Reverse lookup table for status of a show
    stati = {}
    for status, shows in db[ "shows" ].items():
        for show in shows:
            stati[ show[ "title" ] ] = status
    
    remove_hashes = set( cache )
    for hash in remove_hashes:
        if hash not in db[ "torrents" ]:
            anime_manager.filesystem.remove_links(
                cache[ hash ][ "files" ],
                trash,
                dry_run
            )
            cache[ hash ][ "files" ] = {}
            
            server.remove_torrents( ( hash, ), trash, dry_run )
            del cache[ hash ]
    
    for hash in db[ "torrents" ]:
        location = (
            db[ "directories" ][ "torrents" ]
            / year_quarter_for_torrent( db, hash )
        )
        source   = db[ "torrents" ][ hash ][ "source"   ]
        archived = db[ "torrents" ][ hash ][ "archived" ]
        
        check_links = False
        
        if hash not in cache:
            server.add_torrents( ( {
                "source"   : source,
                "location" : location,
                "started"  : not archived,
            }, ), trash, dry_run )
            cache[ hash ] = {
                "source"   : source,
                "location" : location,
                "archived" : archived,
                "files"    : {},
            }
            check_links = True
        
        else:
            if location != cache[ hash ][ "location" ]:
                server.move_torrents( ( {
                    "hash"     : hash,
                    "location" : location,
                }, ), trash, dry_run )
                cache[ hash ][ "location" ] = location
                check_links = True
            
            if source != cache[ hash ][ "source" ]:
                server.source_torrents( ( {
                    "hash"   : hash,
                    "source" : source,
                }, ), trash, dry_run )
                cache[ hash ][ "source" ] = source
            
            if archived != cache[ hash ][ "archived" ]:
                server.status_torrents( ( {
                    "hash"    : hash,
                    "started" : not archived,
                }, ), trash, dry_run )
                cache[ hash ][ "archived" ] = archived
        
        if check_links:
            try:
                name = server.torrent_names( ( hash, ) )[ hash ]
            except anime_manager.torrents.RPCError:
                if dry_run:
                    # Generate placeholder for dry run
                    name = "$TORRENT:{}$".format( hash )
                else:
                    raise
            
            episodes = db[ "torrents" ][ hash ][ "episodes" ]
            files    = {}
            
            for episode in episodes:
                status = stati[ episode[ "show" ][ "title" ] ]
                if "file" in episode:
                    file = episode[ "file" ]
                else:
                    file = pathlib.Path()
                
                source = cache[ hash ][ "location" ] / name / file
                dest   = (
                    db[ "directories" ][ status ]
                    / show_link_for_episode( db, episode )
                # Replace placeholder suffix with source's
                ).with_suffix( source.suffix )
                
                source, dest = relative_link_pair( source, dest )
                
                files[ dest ] = source
            
            # Updating/creating links could be achieved by simply wiping out the
            # old ones & replacing, but I'd rather not potentially recreate a
            # whole bunch of links that are still correct
            
            links_remove = set( cache[ hash ][ "files" ] ) - set( files )
            links_add    = {}
            
            for dest, source in files.items():
                if dest not in cache[ hash ][ "files" ]:
                    links_add[ dest ] = source
                elif cache[ hash ][ "files" ][ dest ] != source:
                    links_remove.add( dest )
                    links_add[ dest ] = source
            
            anime_manager.filesystem.remove_links(
                links_remove,
                trash,
                dry_run
            )
            for link in links_remove:
                del cache[ hash ][ "files" ][ link ]
            
            anime_manager.filesystem.add_links( links_add, trash, dry_run )
            for dest, source in links_add.items():
                cache[ hash ][ "files" ][ dest ] = source
