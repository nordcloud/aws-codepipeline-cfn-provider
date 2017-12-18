import json

import boto3
import os

from boto3.session import Session
import botocore
from cfn_flip import to_json

from utils.logging_utils import get_logger

logger = get_logger()
ROLE_SESSION_PREFIX = 'infra-pipeline'


def setup_s3_client(job_data):
    """Creates an S3 client

    Uses the credentials passed in the event by CodePipeline. These
    credentials can be used to access the artifact bucket.

    :param job_data: The job data structure
    :return: An S3 client with the appropriate credentials

    """
    try:
        key_id = job_data['artifactCredentials']['accessKeyId']
        key_secret = job_data['artifactCredentials']['secretAccessKey']
        session_token = job_data['artifactCredentials']['sessionToken']
        session = Session(aws_access_key_id=key_id,
                          aws_secret_access_key=key_secret,
                          aws_session_token=session_token)
    except Exception as e:
        logger.warn('No credentials in artifact - using default role access: {}'.format(e))
        session = Session()

    return session.client('s3', config=botocore.client.Config(signature_version='s3v4'))


def file_to_dict(filename, data):
    """Converts JSON file to dict

    :param filename: filename
    :param data: string
    :return: dict object
    """
    try:
        try:
            json_data = to_json(data)
            return json.loads(json_data)
        except Exception as _:
            return json.loads(data)
    except Exception as error:
        logger.error("Failed to parse s3 file {}, error: {}".format(filename, str(error)))
        raise ValueError("Unable to load JSON file {} error: {}".format(filename, str(error)))


def put_template_into_s3(job_id, file_name, template):
    """Uploads cfn template to s3 bucket

    :param job_id: pipeline job id
    :param file_name: template file name
    :param template: template dict
    :return: URL to inserted file
    """
    client = boto3.client('s3')
    bucket = os.environ.get('PIPELINE_TEMPLATES_BUCKET')
    key = "{}/{}.json".format(job_id, file_name)
    client.put_object(Bucket=bucket, Key=key, Body=template)
    region = client.get_bucket_location(Bucket=bucket)['LocationConstraint']
    return "https://s3.{}.amazonaws.com/{}/{}".format(region, bucket, key)


def build_role_arn(account, role_name):
    """Build role arn

    :param account: AWS account ID
    :param role_name: role name
    :return: string
    """
    if role_name is None or account is None:
        return None
    return "arn:aws:iam::{}:role/{}".format(account, role_name)
