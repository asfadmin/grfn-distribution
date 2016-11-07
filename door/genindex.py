#!/usr/bin/python

import boto3
import yaml
from jinja2 import Template


def get_links(bucket_name, expire_time_in_seconds):
    s3_client = boto3.client('s3')
    bucket = boto3.resource('s3').Bucket(bucket_name)

    links = []
    for obj in bucket.objects.all():
        url = s3_client.generate_presigned_url(
            ClientMethod='get_object',
            Params = {
                 'Bucket': obj.bucket_name,
                 'Key': obj.key,
            },
            ExpiresIn = expire_time_in_seconds
        )
        links.append({'text': obj.key, 'url': url})
    return links


def get_content(content_config):
    with open(content_config['template_file'], 'r') as t:
        template_text = t.read()
    links = get_links(content_config['bucket_name'], content_config['expire_time_in_seconds'])
    template = Template(template_text)
    content = template.render(links=links)
    return content


def get_config(config_file_name):
    with open(config_file_name, 'r') as f:
        config = yaml.load(f)
    return config


if __name__ == "__main__":
    config = get_config('door_config.yaml')
    content = get_content(config['content'])
    with open(config['output_html_file'], 'w') as f:
        f.write(content)

