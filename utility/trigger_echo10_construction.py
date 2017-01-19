# utility script to trigger grfn-echo10-construction for an arbitrary list of granules
# not production quality, use at your own risk

import boto3
import json
import time

lambda_arn = 'arn:aws:lambda:us-west-2:765666652335:function:grfn-echo10-construction:DEV'
private_bucket = 'grfn-d-fe9f1b34-1425-56b9-939f-5f1431a6d1de'
public_bucket = 'grfn-d-b6710a78-8fc7-5e52-bdc3-b7ea3b691575'
sleep_time_in_seconds = 2

granules = [
'S1-IFG_STCM1S1_TN035_20161208T020720-20170101T020747_s2-resorb-v1.0.1',
'S1-IFG_STCM1S1_TN035_20161208T020720-20170101T020747_s3-resorb-v1.0.1',
'S1-IFG_STCM1S1_TN064_20161210T014940-20170103T015006_s1-resorb-v1.0.1',
]


def unw_geo_payload(granule):
    return {
      'collection': 'Sentinel-1 Unwrapped Interferogram and Coherence Map (BETA)',
      'zip': {
          'key': granule + '.unw_geo.zip',
          'bucket': private_bucket,
       },
       'browse': {
          'key': granule + '.unw_geo.browse.png',
          'bucket': public_bucket,
       },
       'log': {
          'key': granule + '.isce.log',
          'bucket': private_bucket,
       }
    }


def full_res_payload(granule):
    return {
      'collection': 'Sentinel-1 Full Resolution Wrapped Interferogram and DEM (BETA)',
      'zip': {
          'key': granule + '.full_res.zip',
          'bucket': private_bucket,
       },
       'browse': {
          'key': granule + '.full_res.browse.png',
          'bucket': public_bucket,
       },
       'log': {
          'key': granule + '.isce.log',
          'bucket': private_bucket,
       }
    }


def invoke_lambda(lambda_arn, payload):
    region_name = lambda_arn.split(':')[3]
    lambda_client = boto3.client('lambda', region_name=region_name)
    lambda_client.invoke(FunctionName=lambda_arn, InvocationType='Event', Payload=json.dumps(payload))


if __name__ == "__main__":
    for granule in granules:
        print(granule)
        payload = unw_geo_payload(granule)
        invoke_lambda(lambda_arn, payload)
        payload = full_res_payload(granule)
        invoke_lambda(lambda_arn, payload)
        time.sleep(sleep_time_in_seconds)

