from M2Crypto import EVP
import base64
import time


def aws_url_base64_encode(msg):
    msg_base64 = base64.b64encode(msg)
    msg_base64 = msg_base64.replace('+', '-')
    msg_base64 = msg_base64.replace('=', '_')
    msg_base64 = msg_base64.replace('/', '~')
    return msg_base64


def sign_string(message, private_key_string):
    key = EVP.load_key_string(private_key_string)
    key.reset_context(md='sha1')
    key.sign_init()
    key.sign_update(str(message))
    signature = key.sign_final()
    return signature


def create_url(url, encoded_signature, key_pair_id, expires):
    signed_url = '%(url)s&Expires=%(expires)s&Signature=%(encoded_signature)s&Key-Pair-Id=%(key_pair_id)s' % {
            'url':url,
            'expires':expires,
            'encoded_signature':encoded_signature,
            'key_pair_id':key_pair_id,
            }
    return signed_url


def get_canned_policy_url(url, private_key_string, key_pair_id, expires):
    canned_policy = '{"Statement":[{"Resource":"%(url)s","Condition":{"DateLessThan":{"AWS:EpochTime":%(expires)s}}}]}' % {'url':url, 'expires':expires}
    encoded_policy = aws_url_base64_encode(canned_policy)
    signature = sign_string(canned_policy, private_key_string)
    encoded_signature = aws_url_base64_encode(signature)
    signed_url = create_url(url, encoded_signature, key_pair_id, expires);
    return signed_url


key_pair_id = 'APKAINVNJF4BDB5SS5QQ'
private_key_file = '/home/ec2-user/private-key.pem'
url = 'https://d2pislrkqozf6c.cloudfront.net/test.txt?userid=asjohnston'
expire_time_in_seconds = 60

expires = int(time.time()) + expire_time_in_seconds
private_key_string = open(private_key_file).read()
signed_url = get_canned_policy_url(url, private_key_string, key_pair_id, expires)

print(signed_url)
