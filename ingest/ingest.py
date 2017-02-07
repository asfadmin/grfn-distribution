#!/usr/bin/python

import boto3
import zipfile
import os
import time
import yaml
import argparse
import asf.log
import logging
import re
import json
import mimetypes
import tempfile, shutil
import sys

log = logging.getLogger()

class SetupError(Exception):
    pass

def create_output_zip_file(output_file_name, input_zip_handle, files):
    with zipfile.ZipFile(output_file_name, 'w') as output_zip_handle:
        for f in files:
            output_zip_handle.writestr(f['dest'], input_zip_handle.read(f['source']))


def create_output_file(output_file_name, input_zip_handle, file_name):
    with open(output_file_name, 'w') as f:
        f.write(input_zip_handle.read(file_name))
 

def get_bucket(bucket_name):
    return boto3.resource('s3').Bucket(bucket_name)


def upload_object(bucket_name, key):
    bucket = get_bucket(bucket_name)
    content_type = mimetypes.guess_type(key)[0]
    bucket.upload_file(key, key, ExtraArgs={'ContentType': content_type})


def process_output_file(output_file_config, input_zip_handle):
    log.info('Processing output file {0}'.format(output_file_config['key']))
    if 'files' in output_file_config:
        create_output_zip_file(output_file_config['key'], input_zip_handle, output_file_config['files'])
    else:
        create_output_file(output_file_config['key'], input_zip_handle, output_file_config['file'])
    upload_object(output_file_config['bucket'], output_file_config['key'])
    os.remove(output_file_config['key'])
    log.info('Done processing output file {0}'.format(output_file_config['key']))


def process_input_file(obj, output_file_configs, master_bucket):
    unprefixed_name = os.path.basename(obj.key)
    log.info("saving remote file to "+unprefixed_name)
    obj.download_file(unprefixed_name)
    with zipfile.ZipFile(unprefixed_name, 'r') as input_zip_handle:
        for output_file_config in output_file_configs:
            process_output_file(output_file_config, input_zip_handle)
    # TODO figure out what to do with the original
    upload_object(master_bucket, unprefixed_name)
    os.remove(unprefixed_name)


def get_object_from_queue(ingest_queue_name):
    sqs = boto3.resource('sqs')
    queue = sqs.get_queue_by_name(QueueName=ingest_queue_name)

    for message in queue.receive_messages():
        message_body = json.loads(message.body)
        queue_data = message_body['Records'][0]['s3']
        log.info("Processing queue ingest for {0}/{1}".format(queue_data['bucket']['name'], queue_data['object']['key']))
        return boto3.resource('s3').Object(queue_data['bucket']['name'], queue_data['object']['key']), message

    return None, None

def get_object_from_bucket(landing_bucket_name, suffixes):
    landing_bucket = get_bucket(landing_bucket_name)
    for object_summary in landing_bucket.objects.all():
        for suffix in suffixes:
            if object_summary.Object().key.endswith(suffix):
                log.info("Found {0}: {1}".format(suffix, object_summary.Object().key))
                return object_summary.Object(), None
    return None, None


def get_config(config_file_name):
    with open(config_file_name, 'r') as f:
        config = yaml.load(f)
    return config
 

def get_command_line_options():
    parser = argparse.ArgumentParser('Ingest Sentinel-1 interferogram products')
    parser.add_argument(
        '-c', '--config',
        action = 'store',
        dest = 'config_file',
        default = 'ingest_config.yaml',
        help = 'use a specific config file',
    )
    options = parser.parse_args()
    return options


def get_logger(log_config):
    return asf.log.getLogger(**log_config)


def invoke_lambda(lambda_function, payload):
    lambda_client = boto3.client('lambda')
    lambda_client.invoke(FunctionName=lambda_function, InvocationType='Event', Payload=json.dumps(payload))


def process_cmr_reporting(cmr_config):
    for granule in cmr_config['granules']:
        invoke_lambda(cmr_config['lambda_function'], granule)


def format_config(config, object_key):
    tokens = {'$NAME': os.path.splitext(object_key)[0]}
    config_str = str(config)
    for key, value in tokens.iteritems():
        config_str = config_str.replace(key, value)
    return yaml.load(config_str)


def ingest_item(ingest_config):
    process_dir = None
    success_flag = False
    try: 
        if 'ingest_queue_name' in ingest_config:
            obj,msg = get_object_from_queue(ingest_config['ingest_queue_name'])
        elif 'landing_bucket_name' in ingest_config:
            obj,msg = get_object_from_bucket(ingest_config['landing_bucket_name'], ingest_config['landing_bucket_search_suffixes'])
        else:
            log.fatal('Could not divine input source, no queue or landing bucket specified.')
            raise SetupError("No Input source")
      
        if obj:
            process_dir = tempfile.mkdtemp(prefix='GRFN_', dir=ingest_config['working_directory'])
            log.info('Processing in temp dir: {0}'.format(process_dir))
            os.chdir(process_dir)

            unprefixed_name = os.path.basename(obj.key)
            log.info('Processing input file {0}'.format(unprefixed_name))
            formatted_config = format_config(ingest_config, unprefixed_name)
            process_input_file(obj, formatted_config['output_files'], formatted_config['private_content_bucket_name'])
            process_cmr_reporting(formatted_config['cmr'])
            if msg:
                msg.delete()
            obj.delete()
            log.info('Done processing input file {0}'.format(unprefixed_name))

        else:
            time.sleep(ingest_config['sleep_time_in_seconds'])

        success_flag = True

    except zipfile.BadZipfile as e:
        log.warn("Zip file {0} appears to be corrupt. Moving on ...".format(obj.key))
    except zipfile.LargeZipFile as e:
        log.warn("Encountered zip file, {0}, too large to process right now. Moving on ...".format(obj.key))
    except Exception as e:
        log.exception('Unhandled exception: {0}'.format(e))
        log.warn("Failed to process job. Moving on ...");

    if process_dir:
       try: 
          os.chdir(ingest_config['working_directory'])
          shutil.rmtree(process_dir)
       except Exception as e:
          log.warn("Unable to clean up temporary processing directory: {0}".format(process_dir))
          log.exception(e)

    return success_flag

def ingest_loop(ingest_config):
    error_count = 0 
    while True:
       if ingest_item(ingest_config):
           error_count = 0
       else: 
           error_count += 1
   
       if error_count >= ingest_config['max_repeat_errors']:
           log.error("Hit max number of repeat failures: {0}, exiting for health reason".format(error_count));
           return

def setup():
    options = get_command_line_options()
    config = get_config(options.config_file)
    log = get_logger(config['log'])
    boto3.setup_default_session(region_name=config['aws_region'])
    for type, ext in config['extra_mime_types'].iteritems():
        mimetypes.add_type(type, ext)
    return config


if __name__ == "__main__":
    try:
        config = setup()
    except SetupError as e:
        log.error("Cannot proceed from configuration error: {0}".format(e))
        raise
    except:
        log.exception('Unhandled exception!')
        raise

    ingest_loop(config['ingest'])

