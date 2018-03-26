import json
from os import environ
from logging import getLogger
import boto3
from datetime import datetime, timedelta, date
from jinja2 import Template


log = getLogger()
ses = boto3.client('ses')
sqs = boto3.resource('sqs')
dynamodb = boto3.client('dynamodb')


def setup():
    config = json.loads(environ['CONFIG'])
    log.setLevel(config['log_level'])
    log.debug('Config: %s', str(config))
    return config


def build_acknowledgement_email_body(config):
    with open(config['template_file'], 'r') as t:
        template_text = t.read()
    template = Template(template_text)
    email_body = template.render(hostname=config['hostname'])
    return email_body


def get_user(user_id, table):
    results = dynamodb.get_item(
        TableName=table,
        Key={'user_id': {'S': user_id}},
        ProjectionExpression='email_address, last_acknowledgement, subscribed_to_emails',
    )
    if 'Item' not in results:
        return None

    item = results['Item']
    user = {
        'user_id': user_id,
        'email_address': item['email_address']['S'],
    }
    if 'last_acknowledgement' in item:
        user['last_acknowledgement'] = item['last_acknowledgement']['S']
    if 'subscribed_to_emails' in item:
        user['subscribed_to_emails'] = item['subscribed_to_emails']['BOOL']
    else:
        user['subscribed_to_emails'] = True
    return user


def update_last_acknowledgement_for_user(user_id, table):
    primary_key = {'user_id': {'S': user_id}}
    dynamodb.update_item(
        TableName=table,
        Key=primary_key,
        UpdateExpression='set last_acknowledgement = :1',
        ExpressionAttributeValues={
            ':1': {'S': str(datetime.utcnow())},
        },
    )


def send_acknowledgement_email(data, config):
    user = get_user(data['user_id'], config['users_table'])
    if user['subscribed_to_emails']:
        cutoff_date = str(datetime.utcnow() - timedelta(minutes=config['message_interval_in_minutes']))
        if 'last_acknowledgement' not in user or user['last_acknowledgement'] < cutoff_date:
            log.info('Emailing user %s at %s', user['user_id'], user['email_address'])
            ses_message = build_acknowledgement_email(user['email_address'], config)
            ses.send_email(**ses_message)
            update_last_acknowledgement_for_user(user['user_id'], config['users_table'])
    else:
        log.info('User %s is not subscribed to notifications, skipping', user['user_id'])


def build_acknowledgement_email(to_email, config):
    today = date.strftime(datetime.utcnow(), '%B %d, %Y')
    from_email = '{0} <{1}>'.format(config['from_description'], config['from_email'])
    subject = 'SAR Products Requested {0} UTC'.format(today)
    email_body = build_acknowledgement_email_body(config['email_body'])

    ses_message = {
        'Source': from_email,
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


def process_sqs_message(sqs_message, config):
    payload = json.loads(sqs_message.body)
    if payload['type'] == 'acknowledgement':
        send_acknowledgement_email(payload['data'], config)
    #TODO trap errors


def process_notifications(config):
    queue = sqs.Queue(config['email_queue_url'])

    while True:
        messages = queue.receive_messages(MaxNumberOfMessages=config['max_messages_per_receive'], WaitTimeSeconds=config['wait_time_in_seconds'])
        if not messages:
            log.info('No messages found.  Exiting.')
            break

        for sqs_message in messages:
            process_sqs_message(sqs_message, config['email_content'])
            sqs_message.delete()


def lambda_handler(event, context):
    config = setup()
    process_notifications(config['notifications'])
