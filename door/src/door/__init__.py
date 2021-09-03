from flask import Flask

app = Flask(__name__)

from door import routes  # noqa Has to be at end of file or will cause circular import

__all__ = [
    'app',
    'routes',
]
