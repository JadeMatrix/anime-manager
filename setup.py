"""setuptools script for anime_manager"""

import setuptools

setuptools.setup(
    name = "anime_manager",
    version = "1.0.dev",
    author = "JadeMatrix",
    author_email = "jadematrix.art@gmail.com",
    description = (
        "A daemon for automatically managing anime torrents in Deluge"
    ),
    # long_description = ( "" ),
    url = "http://www.jadematrix.com/",
    
    packages = setuptools.find_packages(),
    
    install_requires = [
        "watchdog",
        "PyYAML"
    ]
)
