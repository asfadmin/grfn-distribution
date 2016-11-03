#!/usr/bin/python

import boto3
from jinja2 import Template

bucket_name = 'grfn-d-fe9f1b34-1425-56b9-939f-5f1431a6d1de'
expire_time_in_seconds = 86400
output_html_name = '/var/www/html/index.html'
template_file = 'index.html.template'


def get_links():
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


def get_content():
    with open(template_file, 'r') as t:
        template_text = t.read()
    links = get_links()
    template = Template(template_text)
    content = template.render(links=links)
    return content


if __name__ == "__main__":
    content = get_content()
    with open(output_html_name, 'w') as f:
        f.write(content)

