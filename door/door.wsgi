import sys
import os
sys.path.insert(0, '/var/www/door')

def application(environ, start_response):
    os.environ['URS_USERID']  = environ.get('URS_USERID', '')
    os.environ['DOOR_CONFIG'] = environ.get('DOOR_CONFIG', '')
    from door import app as _application
    return _application(environ, start_response)
