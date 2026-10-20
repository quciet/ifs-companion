"""Activate only the libraries declared by the launched official tool."""
import os
import site

for directory in os.environ.get('IFS_SHARED_LIBRARY_PATHS', '').split(os.pathsep):
    if directory:
        site.addsitedir(directory)
