import boto3

bucket_name = 'grfn-d-fe9f1b34-1425-56b9-939f-5f1431a6d1de'
expire_time_in_seconds = 86400
output_html_name = '/var/www/html/index.html'

license_name = '/var/www/html/sentinel_terms.txt'
with open(license_name, 'r') as st:
   eula_text = st.read()

s3_client = boto3.client('s3')
bucket = boto3.resource('s3').Bucket(bucket_name)

files = []
for obj in bucket.objects.all():
    url = s3_client.generate_presigned_url(
        ClientMethod='get_object',
        Params = {
             'Bucket': obj.bucket_name,
             'Key': obj.key,
        },
        ExpiresIn = expire_time_in_seconds
    )
    files.append({'key': obj.key, 'url': url})

with open(output_html_name, 'w') as f:
    f.write('<html>\n')
    f.write('<head>\n')
    f.write('</head>\n')
    f.write('<body>\n')
    f.write('<pre>\n')
    f.write(eula_text)   
    f.write('</pre>\n')
    for file in files:
        f.write('<a href="{0}">{1}</a>\n'.format(file['url'], file['key']))
        f.write('<br />\n')
    f.write('</body>\n')
    f.write('</html>\n')
