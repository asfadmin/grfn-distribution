import serverless_wsgi

from door import app


serverless_wsgi.TEXT_MIME_TYPES.append('application/problem+json')


def handler(event, context):
    return serverless_wsgi.handle_request(app, event, context)
