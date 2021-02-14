# Database Format

The database consists of a single [YAML](https://yaml.org/) file.  The root node is a dictionary with three main items, all required:

* `directories`
* `shows`
* `torrents`

## Directories

`directories` is a dictionary that configures where the library sections are stored.  It has several optional items: `media`, `torrents`, `trash`, and one item for each of your preferred watching statuses.

The `media` directory is the default library "root" under which other directories are placed; it defaults to the current working directory.  It is suggested you set this to the absolute directory you'd like your entire library stored under.

The rest of the directories can be either absolute or relative paths.  If they are relative, the path is treated as relative to `media`.

`torrents` is the top-level directory for all downloaded torrents; it defaults to `.Torrents/`.  Each individual torrent will be placed in a subdirectory named after the year & quarter of the oldest season with episodes in that torrent.  For example, if a torrent contains episodes from Fall 2020 and Spring 2018, the subdirectory will be `2018q2/`.  (If no year/quarter can be determined from the database, `9999q9/` will be used.)

`trash` is where torrent files no longer managed by the database are placed; it defaults to `.Trash/`.  Each torrent download is placed in a subdirectory starting with a random [UUID](https://en.wikipedia.org/wiki/Universally_unique_identifier) followed by the full original path to that download.

The rest of the items are the directories under which shows in that watch "status" will be placed.  The default name for each is the "status" key in title case (e.g. `in progress` becomes `In Progress`).  You can split up your shows however you want as long as there is at least one "status."


## Shows

`shows` is a dictionary with an item for each watching "status," each of which holds a list of series.

Each series is a dictionary with two keys: `title` and `seasons`.  It should also have a YAML anchor so that torrent entries can refer to it.  The `title` must be unique, as this is used as the name of the directory under which to place its season directories.

`seasons` is a list, with each item being a dictionary with the following keys:

* `year` (required) — year in which the season started airing
* `season` (required) — name of the quarter in which the season started airing (`winter`, `spring`, `summer`, or `fall`)
* `episodes` (optional) — total episode count for that season; if it is present, it is used for the default 0-padding for episode numbers (e.g. `01`)
* `title` (optional) — override for the title of that season; by default the show title is used, with ` - Season <number>` appended for shows with more than one season
* `mal` (suggested, unused) — [MyAnimeList](https://myanimelist.net/) ID for that season
* `anilist` (suggested, unused) — [AniList](https://anilist.co/) ID for that season


## Torrents

`torrents` is a dictionary containing download information & episode mappings.  Each key is the torrent's hash ID; while hashes are not case-sensitive, YAML dictionary keys are, so these should either be all uppercase or all lowercase.  Each item is a dictionary with two required keys — `source` and `episodes` — and and optional `status` key.

`source` is the download URN or path for the torrent metadata.  It can either be a URL, magnet link, or filename; it is passed to Transmission as-is.

`episodes` contains a list of mappings of files in the torrent to episodes.  There are two general mapping formats — manual and pattern-based — which are described in the next two sections.

`status` allows manually setting a download status for that torrent (see [*Automatic torrent management*](Usage.md#Automatic-torrent-management)).  The possible values are:

* `started` — the torrent will be started and never automatically stopped
* `stopped` — the torrent will be paused and never automatically restarted
* `checking` — the torrent will be re-checked for broken or mising files; this is typically only useful temporarily (e.g. for library recovery) as a re-check will be triggered every time an update is run


### Manual mappings

This is the simpler of the two, and maps a single item in the torrent to a single episode.

The only required item is `show`; this must follow the format of a show item from the top-level `shows`, and is intended to be a YAML alias to the appropriate anchor.

The `season` and `episode` items denote the 1-indexed season and episode number; if either are not present they default to 1.  `episode` can also be a string, which is useful for specials not included in the main episode count for a season.

By default the download name of the torrent is used as the episode file, which works for single-episode-single-file torrents.  The `file` item can be used to specify a file in the torrent to use instead.

An optional `alt` item may be used to specify an additional subdirectory under the show directory (such as `720p` vs. `1080p`).  If no `alt` is specified no additional subdirectory is inserted.


### Pattern-based mappings

As for manual mappings, the `show` item is required.

A `pattern` item is a dictionary containing pattern & capture information.  Only regex patterns are currently supported; the regex string is keyed to `regex` and is required.  This pattern will be used to match filenames in the torrent.  Note that regex escape sequences must be double-escaped (`\\`) as YAML uses the same escape character.

`season`, `episode`, and `alt` can be specified under `pattern`; these will be used as default values if there is no match for each.

`matches` contains a dictionary of capture mappings.  Any of `season`, `episode`, and `alt` can be keys, each being a dictionary with one `group` item (for regex patterns).  This item is the index of the capture group in the regex; note that capture group 0 would be the entire string.

*Note that only pattern-based mapping is used for a torrent and `season` is extracted from the pattern, the manager will not be able to determine the oldest season for the torrent, which means it will be downloaded to the `9999q9/` subdirectory.*


## Suggested format

```yaml
directories :
  media : /some/absolute/directory/
  
shows :
  rain day :
    - &show104321
      title   : Example Show One
      seasons :
        - year     : 1998
          season   : spring
          mal      : 4321
          anilist  : 104321
          episodes : 8
    
    # ...
  
  in progress :
    - &show105432
      title   : Example Show Two
      seasons :
        - year     : 2018
          season   : fall
          mal      : 5432
          anilist  : 105432
          episodes : 12
        - year     : 2021
          season   : fall
          mal      : 6543
          anilist  : 106543
          episodes : 12
          title    : "Example Show Two!!"
    
    # ...
  
  archived :
    # ...
  
torrents :
  # Example Show One
  f50d14af29b775f2bac3f6b1f03f2cd17b09cff0 :
    source   : magnet:?xt=urn:f50d14af29b775f2bac3f6b1f03f2cd17b09cff0&…
    episodes :
      - show    : *show104321
        pattern :
          regex   : "Example Show One - (\\d+) \\[[0-9A-F]{8}\\]\\.mp4"
          matches :
            episode :
              group : 1
          season  : 1
  
  # Example Show Two
  9bcc8f9f54f4ceba41a157f9b00c82a68010670f :
    source   : magnet:?xt=urn:9bcc8f9f54f4ceba41a157f9b00c82a68010670f&…
    episodes :
      - show    : *show105432
        season  : 2
        episode : 1
  786a0803365900efccb3cddb982c42daac010fa0 :
    source   : magnet:?xt=urn:786a0803365900efccb3cddb982c42daac010fa0&…
    episodes :
      - show    : *show105432
        season  : 2
        episode : 2
```

Resulting library:

```
/some/absolute/directory/
├── .Torrents
│   ├── 1998q2
│   │   └── Example Show One [DVD][JP|EN]
│   │       ├── Example Show One - 01 [AB6D967E].mp4
│   │       ├── Example Show One - 02 [8BFD0F6D].mp4
│   │       ├── Example Show One - 03 [F7C5BC2F].mp4
│   │       ├── Example Show One - 04 [68276F2D].mp4
│   │       ├── Example Show One - 05 [CB36D532].mp4
│   │       ├── Example Show One - 06 [8AF2D17D].mp4
│   │       ├── Example Show One - 07 [596AFF43].mp4
│   │       ├── Example Show One - 08 [9DE72F53].mp4
│   │       └── credits.txt
│   └── 2021q4
│       ├── [ZZZubz] Example Show Two!! Episode 01 [1080p].mkv
│       └── [ZZZubz] Example Show Two!! Episode 02 [1080p].mkv
├── In Progress
│   └── Example Show Two
│       └── 2 — Example Show Two!!
│           ├── 'Example Show Two!! 01.mkv' -> '../../.Torrents/2021q4/[ZZZubz] Example Show Two!! Episode 01 [1080p].mkv'
│           └── 'Example Show Two!! 02.mkv' -> '../../.Torrents/2021q4/[ZZZubz] Example Show Two!! Episode 02 [1080p].mkv'
└── Rainy Day
    └── Example Show One
        ├── 'Example Show One - 1.mp4' -> '../../.Torrents/1998q2/Example Show One [DVD][JP|EN]/Example Show One - 01 [AB6D967E].mp4'
        ├── 'Example Show One - 2.mp4' -> '../../.Torrents/1998q2/Example Show One [DVD][JP|EN]/Example Show One - 02 [8BFD0F6D].mp4'
        ├── 'Example Show One - 3.mp4' -> '../../.Torrents/1998q2/Example Show One [DVD][JP|EN]/Example Show One - 03 [F7C5BC2F].mp4'
        ├── 'Example Show One - 4.mp4' -> '../../.Torrents/1998q2/Example Show One [DVD][JP|EN]/Example Show One - 04 [68276F2D].mp4'
        ├── 'Example Show One - 5.mp4' -> '../../.Torrents/1998q2/Example Show One [DVD][JP|EN]/Example Show One - 05 [CB36D532].mp4'
        ├── 'Example Show One - 6.mp4' -> '../../.Torrents/1998q2/Example Show One [DVD][JP|EN]/Example Show One - 06 [8AF2D17D].mp4'
        ├── 'Example Show One - 7.mp4' -> '../../.Torrents/1998q2/Example Show One [DVD][JP|EN]/Example Show One - 07 [596AFF43].mp4'
        └── 'Example Show One - 8.mp4' -> '../../.Torrents/1998q2/Example Show One [DVD][JP|EN]/Example Show One - 08 [9DE72F53].mp4'
```
