import boto3
import json
import time
from botocore.exceptions import ClientError

def lambda_handler(event, context):
    if event:
       if not all (k in event for k in ("reset_bucket","reset_queue")):
          print ("no reset bucket or reset queue provided. Please check input")
          return False
         
       s3 = boto3.resource('s3')
       sqs = boto3.resource('sqs')
       sqsc = boto3.client('sqs')
       queue = sqs.get_queue_by_name(QueueName=event["reset_queue"])

       # Theres really no better way to do this?
       try:
          print ("Beginning queue purge")
          queueUrl = sqsc.get_queue_url(QueueName=event["reset_queue"])['QueueUrl']
          sqsc.purge_queue(QueueUrl=queueUrl)
          time.sleep(60)
          print ("Completed queue purge")
 
       except ClientError as e:
          if 'PurgeQueueInProgress' in e.response['Error']['Code']:
             print ("Cannot reset queue, purge in progress. Try again later")
             return False
          raise (e)

       q_cnt = 0
       for item in s3.Bucket(event["reset_bucket"]).objects.all():
          if not item.key.endswith(".zip"):
             continue
          msg = {"Records": [ { "type": "Manual Reset", 
                                "s3": { "bucket": { "name": event["reset_bucket"]}, 
                                        "object": { "key": item.key}}}]} 
          response = queue.send_message(MessageBody=json.dumps(msg))
          print ("Added queue entry for {0}".format(item.key))
          q_cnt += 1
       
       return "Queued {0} items".format(q_cnt)
      
    return False

if __name__ == "__main__":
    lambda_handler( { 'reset_bucket':'grfn-d-a4d38f59-5e57-590c-a2be-58640db02d91',
                      'reset_queue':'GRFN-Ingest-Dev' }, None);
 
