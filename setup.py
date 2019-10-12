"""setuptools script for anime_manager"""

import setuptools

setuptools.setup(
    name = "anime_manager",
    version = "1.1.dev",
    author = "JadeMatrix",
    author_email = "jadematrix.art@gmail.com",
    description = (
        "A daemon for automatically managing anime torrents in Transmission"
    ),
    # long_description = ( "" ),
    url = "http://www.jadematrix.com/",
    
    packages = setuptools.find_packages(),
    entry_points = {
        "console_scripts" : [
            "anime-manager-update = anime_manager:run_update",
            "anime-manager-daemon = anime_manager:run_daemon",
        ],
    },
    
    install_requires = [
        "watchdog>=0.9",
        "PyYAML>=5.1.2",
        "requests>=2.22,<3",
    ]
)
