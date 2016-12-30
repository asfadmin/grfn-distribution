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

log = logging.getLogger()


def send_to_cmr(lambda_arn, payload):
    region_name = lambda_arn.split(':')[3]
    lam = boto3.client('lambda', region_name=region_name)
    lam.invoke(FunctionName=lambda_arn, InvocationType='Event', Payload=json.dumps(payload))


def create_output_zip(source_zip, dest_name, files):
    with zipfile.ZipFile(dest_name, 'w') as dest_zip:
        for f in files:
            dest_zip.writestr(f['dest'], source_zip.read(f['source']))


def create_output_file(source_zip, dest_name, file_name):
    with open(dest_name, 'w') as output_file:
        output_file.write(source_zip.read(file_name))
 

def get_bucket(bucket_name):
    return boto3.resource('s3').Bucket(bucket_name)


def upload_object(bucket_name, key):
    bucket = get_bucket(bucket_name)
    bucket.upload_file(key, key)


def process_output_file(output_file_config, source_zip):
    log.info('Processing output file {0}'.format(output_file_config['key']))
    if 'files' in output_file_config:
        create_output_zip(source_zip, output_file_config['key'], output_file_config['files'])
    else:
        create_output_file(source_zip, output_file_config['key'], output_file_config['file'])
    upload_object(output_file_config['bucket'], output_file_config['key'])
    os.remove(output_file_config['key'])
    log.info('Done processing output file {0}'.format(output_file_config['key']))


def process_input_file(obj, output_file_configs):
    obj.download_file(obj.key)
    with zipfile.ZipFile(obj.key, 'r') as source_zip:
        for output_file_config in output_file_configs:
            process_output_file(output_file_config, source_zip)
    # TODO figure out what to do with the original
    upload_object(output_file_configs[0]['bucket'], obj.key)
    os.remove(obj.key)
    obj.delete()


def get_object_to_ingest(landing_bucket_name):
    landing_bucket = get_bucket(landing_bucket_name)
    for object_summary in landing_bucket.objects.limit(1):
        return object_summary.Object()
    return None


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
    return asf.log.getLogger(screen=log_config['screen'], verbose=log_config['verbose'])


def trigger_cmr_reporting(cmr_config):
    for granule in cmr_config['granules']:
        send_to_cmr(cmr_config['lambda_arn'], granule)


def ingest_loop(ingest_config):
    while True:
        obj = get_object_to_ingest(ingest_config['landing_bucket_name'])
        if obj:
            log.info('Processing input file {0}'.format(obj.key))
            # TODO clean this substitution mess up
            name = os.path.splitext(obj.key)[0]
            output_files = yaml.load(str(ingest_config['output_files']).replace('{name}', name))
            process_input_file(obj, output_files)
            cmr = yaml.load(str(ingest_config['cmr']).replace('{name}', name))
            #trigger_cmr_reporting(cmr)
            log.info('Done processing input file {0}'.format(obj.key))
        else:
            time.sleep(ingest_config['sleep_time_in_seconds'])


if __name__ == "__main__":
    try:
        options = get_command_line_options()
        config = get_config(options.config_file)
        log = get_logger(config['log'])
        os.chdir(config['working_directory'])
        ingest_loop(config['ingest'])
    except:
        log.exception('Unhandled exception!')
        raise

