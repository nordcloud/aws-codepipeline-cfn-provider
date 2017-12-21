import json
import tempfile
import zipfile

import boto3

from utils.aws_utils import file_to_dict
from utils.logging_utils import get_logger

code_pipeline = boto3.client('codepipeline')
logger = get_logger()


class PipelineUserParameters:
    def __init__(self, job_data, lambda_ctx):
        """Decodes the JSON user parameters and validates the required properties passed into Lambda function

        :param job_data: The job data structure containing the UserParameters string which should be a valid JSON structure
        :param lambda_ctx: Lambda context

        Possible ActionMode:
            - CREATE_UPDATE
            - DELETE_ONLY
            - REPLACE_ON_FAILURE
            - CHANGE_SET_REPLACE
            - CHANGE_SET_EXECUTE
        """
        logger.debug("getting user parameters")
        user_parameters = None
        self.TemplateFile = None
        self.TemplateArtifact = None
        self.ConfigFile = None
        self.ConfigArtifact = None
        self.Region = lambda_ctx.invoked_function_arn.split(':')[3]
        self.AccountId = lambda_ctx.invoked_function_arn.split(':')[4]
        try:
            user_parameters = job_data['actionConfiguration']['configuration']['UserParameters']
            decoded_parameters = json.loads(user_parameters)
        except Exception as e:
            raise Exception('UserParameters could not be decoded as JSON: {} {}'.format(user_parameters, str(e)))

        if 'ActionMode' not in decoded_parameters:
            raise Exception('Your UserParameters JSON must include the ActionMode')

        if decoded_parameters['ActionMode'] not in ['CREATE_UPDATE', 'DELETE_ONLY', 'REPLACE_ON_FAILURE',
                                                    'CHANGE_SET_REPLACE', 'CHANGE_SET_EXECUTE']:
            raise Exception("Invalid ActionMode parameter")

        if 'StackName' not in decoded_parameters:
            raise Exception('Your UserParameters JSON must include the StackName')

        if 'ChangeSetName' not in decoded_parameters and decoded_parameters['ActionMode'] \
                in ['CHANGE_SET_REPLACE', 'CHANGE_SET_EXECUTE']:
            raise Exception('Your UserParameters JSON must include the ChangeSetName')

        if 'TemplatePath' not in decoded_parameters and decoded_parameters['ActionMode'] \
                in ['CREATE_UPDATE', 'REPLACE_ON_FAILURE', 'CHANGE_SET_REPLACE']:
            raise Exception('Your UserParameters JSON must include the TemplatePath')

        self.ActionMode = decoded_parameters['ActionMode']
        self.StackName = decoded_parameters['StackName']
        self.ChangeSetName = decoded_parameters.get('ChangeSetName', None)
        self.RoleArn = decoded_parameters.get('RoleArn', None)
        self.OutputFileName = decoded_parameters.get('OutputFileName', 'output.json')
        self.Capabilities = decoded_parameters.get('Capabilities', None)
        try:
            if decoded_parameters.get('TemplatePath', None) is not None:
                self.TemplateArtifact,  self.TemplateFile = decoded_parameters['TemplatePath'].split('::')
        except Exception as _:
            raise Exception('Invalid TemplatePath parameter, should be ArtifactName::TemplateFile')
        try:
            if decoded_parameters.get('ConfigPath', None) is not None:
                self.ConfigArtifact, self.ConfigFile = decoded_parameters['ConfigPath'].split('::')
        except Exception as _:
            raise Exception('Invalid ConfigPath parameter, should be ArtifactName::ConfigFile')
        self.ParameterOverrides = decoded_parameters.get('ParameterOverrides', {})
        if type(self.ParameterOverrides) is not dict:
            raise Exception('Invalid ParameterOverrides parameter, ParametersOverride should be a dict')


class PipelineStackConfig:
    def __init__(self, config, template, override, update=False, capabilities=None):
        """Generates Stack config - parameters, tags and cfn policy
        If update is True and parameter doesn't exist in the config previous value will be used

        :param config: config dict with parameters, stack policy and tags
        :param template: cfn template dict
        :param override: dict with parameters to override
        :param update: True if update
        """
        self.Parameters = config.get('Parameters', {}) if config is not None else {}
        for p in override:
            self.Parameters[p] = override[p]
        self.Tags = config.get('Tags', {}) if config is not None else {}
        self.StackPolicy = config.get('StackPolicy', None) if config is not None else None

        tags = []
        for tag in self.Tags:
            tags.append({'Key': tag, 'Value': self.Tags[tag]})
        self.Tags = tags
        self.Capabilities = capabilities
        self.Update = update

        parameters = []
        if 'Parameters' in template:
            for key_name in template['Parameters'].keys():

                if key_name in self.Parameters:
                    parameters.append({'ParameterKey': key_name,
                                       'ParameterValue': self.Parameters[key_name]})
                elif update:
                    parameters.append({'ParameterKey': key_name,
                                       'UsePreviousValue': True})
        self.Parameters = parameters


class PipelineArtifact:
    def __init__(self, artifact, region):
        """Creates pipeline artifact object

        :param artifact: dict with artifact details
        :param region: region where artifact is stored
        """
        self.name = artifact.get('name')
        self.location = artifact.get('location')
        self.revision = artifact.get('revision')
        self.files = {}
        self.url = "https://s3-{}.amazonaws.com/{}/{}".format(
            region,
            self.location['s3Location']['bucketName'],
            self.location['s3Location']['objectKey']
        )

    def add_file(self, key, data):
        self.files[key] = file_to_dict(key, data)
        return self.files[key]


def load_pipeline_artifacts(artifacts_list, region):
    artifacts = {}
    for artifact in artifacts_list:
        artifacts[artifact['name']] = PipelineArtifact(artifact, region)
    return artifacts


def parse_override_params(s3, params, artifacts):
    """Replaces special overrides functions - Fn::GetArtifactAtt and Fn::GetParam

    :param s3: s3 client
    :param params: list of all override parameters.
    :param artifacts: dict with input parameters
    :return:
    """
    for key in params:
        if type(params[key]) is dict:
            if len(params[key]) != 1:
                raise Exception('Parameters override syntax error ({})'.format(key))
            func = list(params[key].keys())[0]
            if func == 'Fn::GetArtifactAtt':
                params[key] = get_artifact_att(params[key][func], artifacts)
            elif func == 'Fn::GetParam':
                params[key] = get_artifact_param(s3, params[key][func], artifacts)
            else:
                raise TypeError('Parameters override syntax error ({})'.format(key))
    return params


def get_artifact_att(params_list, artifacts):
    """Replaces Fn::GetArtifactAtt function

    :param params_list: list of Fn::GetArtifactAtt arguments
    :param artifacts: dict with input artifacts
    :return: parameter value
    """
    if type(params_list) is not list or len(params_list) != 2:
        raise TypeError("Invalid list of parameters in Fn::GetArtifactAtt")
    try:
        artifact = artifacts[params_list[0]]
        if params_list[1] == 'BucketName':
            return artifact.location['s3Location']['bucketName']
        elif params_list[1] == 'ObjectKey':
            return artifact.location['s3Location']['objectKey']
        elif params_list[1] == 'URL':
            return artifact.url
        else:
            raise TypeError("Failed to override parameter using Fn::GetArtifactAtt - invalid attribute name")
    except Exception as e:
        raise TypeError("Failed to override parameter using Fn::GetArtifactAtt function {}".format(e))


def get_artifact_param(s3, params_list, artifacts):
    """Replaces Fn::GetParam function

    :param s3: s3 client
    :param params_list: list of Fn::GetParam arguments - len should be 3
    :param artifacts: dict with input artifacts
    :return: parameter value
    """
    if type(params_list) is not list or len(params_list) != 3:
        raise TypeError("Invalid list of parameters in Fn::GetParam")
    try:
        file_name, param_name = params_list[1], params_list[2]
        artifact: PipelineArtifact = artifacts[params_list[0]]
        if file_name not in artifact.files:
            get_file_from_artifact(s3, artifact, file_name)
        return artifact.files[file_name][param_name]
    except Exception as e:
        raise TypeError("Failed to override parameter using Fn::GetParam function {}".format(e))


def save_output_artifact(s3, artifact_data, filename, file_data):
    """Saves output artifact in s3 bucket

    :param s3: s3 client
    :param artifact_data: dict with artifact location
    :param filename: output filename
    :param file_data: output data
    """
    bucket = artifact_data['location']['s3Location']['bucketName']
    key = artifact_data['location']['s3Location']['objectKey']

    with tempfile.NamedTemporaryFile() as tmp_file:
        with zipfile.ZipFile(tmp_file.name, 'w') as zip_f:
            zip_f.writestr(filename, file_data)
        s3.upload_file(tmp_file.name, bucket, key, ExtraArgs={'ServerSideEncryption': 'aws:kms'})


def put_job_failure(job, message):
    """Notify CodePipeline of a failed job

    :param job: job ID
    :param message: A message to be logged relating to the job status
    """
    logger.debug('Putting job failure')
    logger.debug(message)
    code_pipeline.put_job_failure_result(jobId=job, failureDetails={'message': message, 'type': 'JobFailed'})


def put_job_success(job, message):
    """Notify CodePipeline of a successful job

    :param job: job ID
    :param message: A message to be logged relating to the job status

    """
    logger.debug('Putting job success')
    logger.debug(message)
    code_pipeline.put_job_success_result(jobId=job)


def continue_job_later(job, message):
    """Notify CodePipeline of a continuing job

    This will cause CodePipeline to invoke the function again with the
    supplied continuation token.

    :param job: job ID
    :param message: A message to be logged relating to the job status
    """
    continuation_token = json.dumps({'previous_job_id': job})

    logger.debug('Putting job continuation')
    logger.debug(message)
    code_pipeline.put_job_success_result(jobId=job, continuationToken=continuation_token)


def get_file_from_artifact(s3, artifact_data: PipelineArtifact, file_name):
    """Downloads file fro martifact

    :param s3: s3 client
    :param artifact_data: artifact object with s3 location etc.
    :param file_name: filename
    :return: file
    """
    if not artifact_data:
        raise ValueError('failed to get file {} from artifact: Artifact not found'.format(file_name))

    bucket = artifact_data.location['s3Location']['bucketName']
    key = artifact_data.location['s3Location']['objectKey']
    try:
        with tempfile.NamedTemporaryFile() as tmp_file:
            s3.download_file(bucket, key, tmp_file.name)

            with zipfile.ZipFile(tmp_file.name, 'r') as zip_f:
                data = zip_f.read(file_name)
                return artifact_data.add_file(file_name, data)
    except Exception as e:
        raise ValueError('failed to get file {} from artifact {}'.format(file_name, str(e)))


def generate_output_artifact(s3, job_data, params: PipelineUserParameters, output_data):
    """Generates output artifact with stack outputs

    :param s3: s3 client
    :param job_data: dict with job details
    :param params: Parameters object with OutputFileName
    :param output_data: dict with output data
    """
    if len(job_data.get('outputArtifacts', [])) > 0:
        artifact = job_data['outputArtifacts'][0]
        save_output_artifact(s3, artifact, params.OutputFileName, json.dumps(output_data))
