import argparse
import pathlib


class AbsPathAction( argparse.Action ):
    """`argparse` action for converting strings to `pathlib.Path`s"""
    def __call__( self, parser, namespace, values, option_string = None ):
        try:
            values = pathlib.Path( values ).resolve()
        except TypeError:
            pass
        setattr( namespace, self.dest, values )

parser = argparse.ArgumentParser(
    description = "JadeMatrix's anime torrent manager"
)

parser.add_argument(
    "-d",
    "--database",
    metavar  = "FILENAME",
    action   = AbsPathAction,
    help     = "YAML torrent database file to watch for changes",
    required = True
)
parser.add_argument(
    "-t",
    "--transmission",
    metavar  = "ADDRESS[:PORT]",
    help     = "Transmission RPC server to use",
    required = True
)
parser.add_argument(
    "-c",
    "--cache-dir",
    metavar  = "DIRNAME",
    action   = AbsPathAction,
    help     = "persistent cache directory",
    required = True
)
parser.add_argument(
    "-g",
    "--log-file",
    metavar  = "FILENAME",
    action   = AbsPathAction,
    help     = "log file to use (defaults to 'log' in the cache directory)",
    required = False
)
parser.add_argument(
    "-l",
    "--log-level",
    metavar  = "LEVEL",
    choices  = [
        "CRITICAL",
        "ERROR",
        "SUCCESS",
        "WARNING",
        "NOTICE",
        "INFO",
        "VERBOSE",
        "DEBUG",
        "SPAM",
        "NOTSET",
    ],
    default  = "INFO",
    help     = "standard Python logging level to use",
    required = False
)
parser.add_argument(
    "-n",
    "--dry-run",
    action   = "store_true",
    help     = "print changes that would be made and exit",
    required = False
)
parser.add_argument(
    "--no-trash",
    action   = "store_true",
    help     = "when removing files/directories, delete rather than trash them",
    required = False
)
