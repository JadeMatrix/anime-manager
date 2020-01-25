import anime_manager.filesystem
import anime_manager.torrents

import logging
import math
import os.path
import pathlib
import time


log = logging.getLogger( __name__ )

season_quarter_map = {
    "winter" : "q1",
    "spring" : "q2",
    "summer" : "q3",
    "fall"   : "q4"
}


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
    
    min = "9999q9"
    
    for episode in db[ "torrents" ][ hash ][ "episodes" ]:
        if "pattern" in episode:
            if "season" in episode[ "pattern" ]:
                season = episode[ "show" ][ "seasons" ][
                    episode[ "pattern" ][ "season" ] - 1
                ]
            else:
                continue
        else:
            season = episode[ "show" ][ "seasons" ][ episode[ "season" ] - 1 ]
        
        candidate = "{}{}".format(
            season[ "year" ],
            season_quarter_map[ season[ "season" ] ]
        )
        if candidate < min:
            min = candidate
    
    return min


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
        padding = int( math.log10( len( show[ "seasons" ] ) ) ) + 1
        if "title" in season:
            link = link / "{:0{}} - {}".format(
                episode[ "season" ],
                padding,
                season [ "title"  ]
            )
        else:
            link = link / "{:0{}} - Season {}".format(
                episode[ "season" ],
                padding,
                episode[ "season" ]
            )
    
    if "episode" in episode:
        episode_number = episode[ "episode" ]
        if issubclass( type( episode_number ), ( str, bytes ) ):
            try:
                episode_number = int( episode[ "episode" ] )
            except ( ValueError, TypeError ):
                pass
    else:
        episode_number = None
    
    if (
        "episodes" in season
        and season[ "episodes" ] == 1
        and episode_number == 1
    ):
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
        use_e = multiseason and not has_season_title
        try:
            padding = (
                int( math.log10( season[ "episodes" ] ) )
                if "episodes" in season else 1
            ) + 1
            try:
                episode_string = "{:0{}d}".format( episode_number, padding )
            except ValueError:
                episode_string = "{:f}".format( episode_number )
                whole, decimal = episode_string.strip( "0" ).split(
                    ".",
                    maxsplit = 1
                )
                episode_string = "{:0{}}.{}".format(
                    int( whole ),
                    padding,
                    decimal if decimal else 0
                )
            if use_e:
                episode_string = "e" + episode_string
        except ValueError:
            episode_string = str( episode_number )
            episode_string = "{}{}".format(
                "e" if use_e and episode_string[ 0 ] in "0123456789" else " ",
                episode_string
            )
        
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


def relative_link_pair( dest, source ):
    """Modify a source & destination so that the source is relative, if possible
    
    Args:
        dest (pathlib.Path):    The filename & path of the symlink (fully
                                prefixed up to the media directory)
        source (pathlib.Path):  The target of the symlink, as cached (fully
                                prefixed up to the media directory)
    
    Returns:
        tuple:  The potentially modified source & destination
    """
    
    common_path = pathlib.Path( os.path.commonpath( ( source, dest ) ) )
    if common_path != common_path.root:
        source = pathlib.Path( os.path.relpath( source, dest.parent ) )
    return dest, source


def expand_episodes( server, db, hash, dry_run = False ):
    """Expand a list of database episode entries
    
    Args:
        server (torrents.TransmissionServer):
                    The Transmission server to use as a reference
        db (dict):  A full, unflattened database
        hash (str): The torrent hash
        dry_run (bool):     Whether to skip actually executing actions
    
    Returns:
        list (dict):    A database list of torrent episodes with patterns
                        expanded
    """
    
    torrent_files = None
    episodes = []
    
    for episode in db[ "torrents" ][ hash ][ "episodes" ]:
        
        if "pattern" in episode:
            pattern = episode[ "pattern" ]
            match_fields = ( "episode", "season", "alt", )
            if torrent_files is None:
                try:
                    torrent_files = server.torrent_files( ( hash, ) )[ hash ]
                except anime_manager.torrents.RPCError:
                    if dry_run:
                        continue
                    else:
                        raise
            
            for torrent_file in torrent_files:
                # File without top-level name, as expected in the database
                file = pathlib.Path( *torrent_file.parts[ 1 : ] )
                
                generated = {
                    "show" : episode[ "show" ],
                    "file" : file,
                }
                for field in match_fields:
                    if field in pattern:
                        generated[ field ] = pattern[ field ]
                
                match = pattern[ "regex" ].search( file.as_posix() )
                if not match:
                    continue
                
                for field in match_fields:
                    if field not in pattern[ "matches" ]:
                        continue
                    
                    try:
                        value = match.group(
                            pattern[ "matches" ][ field ][ "group" ]
                        )
                        if field in ( "episode", "season", ):
                            try:
                                generated[ field ] = int( value )
                                if "offset" in pattern[ "matches" ][ field ]:
                                    generated[ field ] -= (
                                        pattern[ "matches" ][ field ][ "offset" ]
                                    )
                            except ValueError:
                                generated[ field ] = value
                        else:
                            generated[ field ] = value
                    except IndexError:
                        pass
                
                # Skip any files that matched but are missing fields
                if sum( f not in generated for f in ( "episode", "season", ) ):
                    log.warning( (
                        "torrent {!r} file {!r} matched regex {!r} but "
                        "required fields are missing, skipping"
                    ).format(
                        hash,
                        file.as_posix(),
                        pattern[ "regex" ].pattern
                    ) )
                else:
                    episodes.append( generated )
        
        else:
            episodes.append( episode )
    
    return episodes


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
            db[ "torrents" ][ hash ][ "location" ]
            if "location" in db[ "torrents" ][ hash ]
            else pathlib.Path()
        )
        if not location.is_absolute():
            location = (
                db[ "directories" ][ "torrents" ]
                / year_quarter_for_torrent( db, hash )
                / location
            )
        
        source   = db[ "torrents" ][ hash ][ "source"   ]
        archived = db[ "torrents" ][ hash ][ "archived" ]
        
        check_links = True
        
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
        
        else:
            if location != cache[ hash ][ "location" ]:
                server.move_torrents( ( {
                    "hash"     : hash,
                    "location" : location,
                }, ), trash, dry_run )
                cache[ hash ][ "location" ] = location
            
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
            
            files = {}
            
            for episode in expand_episodes( server, db, hash, dry_run ):
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
                
                dest, source = relative_link_pair( dest, source )
                
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
