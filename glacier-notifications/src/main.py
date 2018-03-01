import os
from logging import getLogger
import boto3
import yaml
from datetime import datetime, timedelta
from dateutil.parser import parse


log = getLogger()


EMAIL_TEMPLATE_NEW = '''
Newly available data to download:
<UL>
{0}
</UL>
<p>
'''
EMAIL_TEMPLATE_OLD = '''
Already available for download:
<UL>
{0}
</UL>
<p>
'''
EMAIL_TEMPLATE_WAIT = '''
Data request still in process:
<UL>
{0}
</UL>
<p>
'''
EMAIL_TEMPLATE_FOOTER = '''
Thank you,<br>ASF DAAC
<p>
<a href="{0}">Unsubscribe</a> from email notifications
'''


def get_file_content_from_s3(bucket, key):
    s3 = boto3.resource('s3')
    obj = s3.Object(bucket, key)
    response = obj.get()
    contents = response['Body'].read()
    return contents


def get_maturity(arn):
    arn_tail = arn.split(':')[-1]
    if arn_tail in ['DEV', 'TEST', 'PROD']:
        maturity = arn_tail
    else:
        maturity = 'LATEST'
    return maturity


def get_config(bucket, key):
    config_contents = get_file_content_from_s3(bucket, key)
    return yaml.load(config_contents)


def setup(arn):
    maturity = get_maturity(arn)
    config = get_config(os.environ['CONFIG_BUCKET'], os.environ[maturity])
    log.setLevel(config['log_level'])
    log.debug('Config: %s', str(config))
    return config


def get_restore_requests(table_name):
    dynamodb = boto3.client('dynamodb')
    response = dynamodb.scan(TableName=table_name)
    return response['Items']


def put_restore_date(table_name, request):
    dynamodb = boto3.client('dynamodb')
    primary_key = {'bucket': request['bucket'], 'key': request['key']}
    val = {'S':  str(datetime.now()) }
    dynamodb.update_item(
        TableName=table_name,
        Key=primary_key,
        UpdateExpression='set restore_date = :1',
        ExpressionAttributeValues={':1': val},
    )

def delete_request_record(table_name, request):
    dynamodb = boto3.client('dynamodb')
    primary_key = {'bucket': request['bucket'], 'key': request['key']}
    dynamodb.delete_item(TableName=table_name, Key=primary_key)


def send_notification_for_file(to, files, config):
    ses = boto3.client('ses')
    new, old, wait = [], [], []
    for record in files['new']:
        new.append("<li></b>"+config['download_path'].format(record['key']['S'])+"</b></li>")
    for record in files['old']:
        old.append("<li>"+config['download_path'].format(record['key']['S'])+"</li>")
    for record in files['wait']:
        wait.append("<li>{0}</li>".format(record['key']['S']))

    email_body = EMAIL_TEMPLATE_NEW.format("<br>\n".join(new))
    if files['old']:
        email_body += EMAIL_TEMPLATE_OLD.format("<br>\n".join(old))
    if files['wait']:
        email_body += EMAIL_TEMPLATE_WAIT.format("<br>\n".join(wait))
    email_body += EMAIL_TEMPLATE_FOOTER.format(config['unsubscribe_url'])  

    ses_message = {
        'Source': config['from_email'],
        'Destination': {
            'ToAddresses': [to],
        },
        'Message': {
            'Subject': {
                'Data': 'SAR Product Available to Download',
            },
            'Body': {
                'Html': {
                    'Data': email_body,
                },
            },
        },
    }

    ses.send_email(**ses_message)


def get_object(request):
    s3 = boto3.resource('s3')
    bucket = request['bucket']['S']
    key = request['key']['S']
    obj = s3.Object(bucket, key)
    return obj


def is_available(obj):
    return obj.storage_class != 'GLACIER' or (obj.restore and 'ongoing-request="false"' in obj.restore)

def is_new(request):
    return not 'restore_date' in request

def is_old(request, old_threshold):
    if is_new(request):
        return False
    return parse(request['restore_date']['S']) < ( datetime.now() - timedelta(hours=old_threshold) )

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
    arn = context.invoked_function_arn
    config = setup(arn)
    process_restore_notifications(config['restore_notifications'])
