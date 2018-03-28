import json
from os import environ
from logging import getLogger
import boto3
from datetime import datetime, timedelta, date
from jinja2 import Environment, FileSystemLoader


log = getLogger()
ses = boto3.client('ses')
sqs = boto3.resource('sqs')
dynamodb = boto3.client('dynamodb')
lamb = boto3.client('lambda')


def setup():
    config = json.loads(environ['CONFIG'])
    log.setLevel(config['log_level'])
    log.debug('Config: %s', str(config))
    return config


def render(template_file, data):
    loader = FileSystemLoader('.')
    env = Environment(loader=loader)
    template = env.get_template(template_file)
    return template.render(data=data)


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
        'last_acknowledgement': item['last_acknowledgement']['S'],
        'subscribed_to_emails': item['subscribed_to_emails']['BOOL'],
    }
    return user


def get_objects_for_user(user_id, status_lambda):
    payload = {'user_id': user_id}
    response = lamb.invoke(
        FunctionName=status_lambda,
        Payload=json.dumps(payload),
    )
    objects = json.loads(response['Payload'].read())
    return objects


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


def build_ses_message(email_subject, email_body, email_address, config):
    today = date.strftime(datetime.utcnow(), '%B %d, %Y')
    from_email = '{0} <{1}>'.format(config['from_description'], config['from_email'])
    final_subject = email_subject.format(today)

    ses_message = {
        'Source': from_email,
        'Destination': {
            'ToAddresses': [email_address],
        },
        'Message': {
            'Subject': {
                'Data': final_subject,
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
    log.info('User ID: %s  Type: %s', payload['user_id'], payload['type'])
    user = get_user(payload['user_id'], config['users_table'])

    if not user['subscribed_to_emails']:
        log.info('User %s is not subscribed to notifications, skipping', user['user_id'])
        return

    if payload['type'] == 'acknowledgement':
        cutoff_date = str(datetime.utcnow() - timedelta(minutes=config['message_interval_in_minutes']))
        if cutoff_date <= user['last_acknowledgement']:
            log.info('User %s already notified at %s, skipping', user['user_id'], user['last_acknowledgement'])
            return

    if payload['type'] == 'acknowledgement':
        email_subject = 'SAR Products Requested {0} UTC'
        template = 'acknowledgement.template'
        data = {
            'hostname': config['hostname']
        }
    elif payload['type'] == 'availability':
        email_subject = 'SAR Products Available {0} UTC'
        template = 'availability.template'
        data = {
            'hostname': config['hostname'],
            'objects': get_objects_for_user(user['user_id'], config['status_lambda']),
            'retention_days': config['retention_days'],
        }

    email_body = render(template, data)
    ses_message = build_ses_message(email_subject, email_body, user['email_address'], config['sender'])
    ses.send_email(**ses_message)

    if payload['type'] == 'acknowledgement':
        update_last_acknowledgement_for_user(user['user_id'], config['users_table'])


def process_notifications(config):
    queue = sqs.Queue(config['email_queue_url'])

    while True:
        messages = queue.receive_messages(MaxNumberOfMessages=config['max_messages_per_receive'], WaitTimeSeconds=config['wait_time_in_seconds'])
        if not messages:
            log.info('No messages found.  Exiting.')
            break

        for sqs_message in messages:
            try:
                process_sqs_message(sqs_message, config['email_content'])
                sqs_message.delete()
            except Exception as e:
                log.exception('Failed to process message')


def lambda_handler(event, context):
    config = setup()
    process_notifications(config['notifications'])
