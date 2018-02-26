import sys
import os
sys.path.insert(0, '/var/www/door')

def application(environ, start_response):
    from door import app as _application
    return _application(environ, start_response)
