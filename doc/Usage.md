# Usage

## Installation

It is recommended (but not required) to install `anime_manager` in a [Python virtual environment](https://docs.python.org/3/library/venv.html).

Installation can be done using [`pip`](https://pip.pypa.io/en/stable/) for dependency resolution:

```bash
pip install path/to/clone/
```

This will create two commands:

* `anime-manager-update` — single-pass update script
* `anime-manager-daemon` — persistent daemon that runs update whenever the database file changes


## Running the manager

Run `anime-manager-update --help` to get a list of arguments and their descriptions.  The required arguments are:

* `--database`/`-d` — the [database file](Database%20Format.md) to use
* `--transmission`/`-t` — the [Transmission](https://transmissionbt.com/) RPC server connection information (if no port number is given, the default of `9091` is assumed)
* `--cache-dir`/`-c` — directory in which to place internal generated files (database cache, log files, etc.)

`anime-manager-update` can be run manually or configured to run periodically (e.g. as a [`cron`](https://en.wikipedia.org/wiki/Cron) job).  However, the preferred method is to configure `anime-manager-daemon` as a system service.  An [`rc`](https://www.freebsd.org/cgi/man.cgi?query=rc&sektion=8) service file is provided [here](../scripts/rc/anime-manager) for use on [FreeBSD](https://www.freebsd.org/)-based systems (such as [FreeNAS](https://www.freenas.org/)/[TrueNAS CORE](https://www.truenas.com/)).  A [`systemd`](https://www.freedesktop.org/wiki/Software/systemd/) unit file for [Linux-based systems](https://en.wikipedia.org/wiki/Linux_distribution) is currently a TODO item.


## Automatic torrent management

The manager currently uses a hard-coded heuristic for automatically stopping & restarting torrents:

* Status is set to `checking` if the torrent has not started
* Status is set to `started` if:
    * the torrent is less than 100% downloaded
    * there are fewer than 1 seeders
    * your upload ratio is less than 2.0
* Otherwise status is set to `stopped`

Each condition is re-checked on update.  The automatic status can be overridden using the [per-torrent `status` item in the database](Database%20Format.md#Torrents).
