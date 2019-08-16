import errno
import os


def mkdir_p( directory ):
    """Like `mkdir -p`, makes a directory and is a no-op if the directory exists
    
    Args:
        directory (str): The directory to make
    """
    
    try:
        os.makedirs( directory )
    except OSError as e:
        if not (
            e.errno == errno.EEXIST
            and os.path.isdir( directory )
        ):
            raise
