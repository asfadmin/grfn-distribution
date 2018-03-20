import json
from os import environ
from logging import getLogger
import boto3
from datetime import datetime, timedelta, date
from dateutil.parser import parse
from jinja2 import Template

log = getLogger()
ses = boto3.client('ses')


def setup():
    config = json.loads(environ['CONFIG'])
    log.setLevel(config['log_level'])
    log.debug('Config: %s', str(config))
    return config


def get_restore_requests(table_name):
    dynamodb = boto3.client('dynamodb')
    response = dynamodb.scan(TableName=table_name)
    return response['Items']


def build_acknowledgement_email_body(config):
    with open(config['template_file'], 'r') as t:
        template_text = t.read()
    template = Template(template_text)
    email_body = template.render(hostname=config['hostname'])
    return email_body


def send_acknowledgement_email(to_email, config):
    ses_message = build_acknowledgement_email(to_email, config)
    ses.send_email(**ses_message)


def build_acknowledgement_email(to_email, config):
    today = date.strftime(datetime.utcnow(), '%B %d, %Y') #TODO deal with time zones
    subject = 'SAR Products Requested {0}'.format(today)
    email_body = build_acknowledgement_email_body(config['email_body'])

    ses_message = {
        'Source': config['from_email'],
        'Destination': {
            'ToAddresses': [to_email],
        },
        'Message': {
            'Subject': {
                'Data': subject,
            },
            'Body': {
                'Html': {
                    'Data': email_body,
                },
            },
        },
    }
    return ses_message


def process_restore_notifications(config):
    emails = {}
    for request in get_restore_requests(config['db_table']):
        obj = get_object(request)
        addresses = request['email_addresses']['SS']
        if is_old(request, 24):
            delete_request_record(config['db_table'], request)
            continue
        for address in addresses:
            if not address in emails:
                emails[address] = { 'new': [], 'old': [], 'wait': [] }
        if is_new(request):
            if is_available(obj):
                put_restore_date(config['db_table'], request)
                for address in addresses:
                    emails[address]['new'].append( request )
            else:
                for address in addresses:
                    emails[address]['wait'].append( request )
        else:
            for address in addresses:
                emails[address]['old'].append( request )

    for email in emails:
        if emails[email]['new']:
            log.warning('Sending notifications to %s', email)
            send_notification_for_file(email, emails[email], config['email'])


def lambda_handler(event, context):
    config = setup()
    process_restore_notifications(config['restore_notifications'])
