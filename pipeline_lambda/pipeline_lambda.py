from __future__ import print_function

import json
import traceback

import boto3

from utils.aws_utils import setup_s3_client, put_template_into_s3
from utils.pipeline_utils import put_job_failure, put_job_success, continue_job_later, \
    PipelineUserParameters, PipelineStackConfig, load_pipeline_artifacts, \
    parse_override_params, get_file_from_artifact, generate_output_artifact
from utils.stack_utils import stack_exists, get_stack_status, \
    stack_delete, change_set_exists, execute_change_set, get_change_set_status, delete_change_set, create_change_set, \
    update_stack, create_stack, get_stack_output

from utils.logging_utils import get_logger

logger = get_logger()


def start_stack_create_or_update(cf, job_id, stack_name, template_url, config: PipelineStackConfig,
                                 update=False, role_arn=None):
    if update:
        status = get_stack_status(cf, stack_name)
        if status not in ['CREATE_COMPLETE', 'ROLLBACK_COMPLETE', 'UPDATE_COMPLETE', 'UPDATE_ROLLBACK_COMPLETE']:
            put_job_failure(job_id, 'Stack cannot be updated when status is: ' + status)
            return
        if update_stack(cf, stack_name, template_url, config, role_arn):
            continue_job_later(job_id, 'Stack update started')
        else:
            continue_job_later(job_id, 'There were no stack updates')
    else:
        create_stack(cf, stack_name, template_url, config, role_arn)
        continue_job_later(job_id, 'Stack create started')


def check_stack_status(cf, job_id, stack):
    status = get_stack_status(cf, stack)
    if status in ['UPDATE_COMPLETE', 'CREATE_COMPLETE']:
        put_job_success(job_id, 'Stack completed')
        return True
    elif status in ['UPDATE_IN_PROGRESS', 'UPDATE_ROLLBACK_IN_PROGRESS',
                    'UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS', 'CREATE_IN_PROGRESS',
                    'ROLLBACK_IN_PROGRESS', 'DELETE_IN_PROGRESS', 'UPDATE_COMPLETE_CLEANUP_IN_PROGRESS']:
        continue_job_later(job_id, 'Stack still in progress: {}'.format(status))
    elif status in ['REVIEW_IN_PROGRESS']:
        put_job_failure(job_id, 'Stack in REVIEW_IN_PROGRESS state')
    else:
        put_job_failure(job_id, 'Stack failed: {}'.format(status))
    return False


def generate_template_and_config(s3, cf, job_id, params: PipelineUserParameters, in_artifacts):
    template = get_file_from_artifact(s3, in_artifacts.get(params.TemplateArtifact), params.TemplateFile)
    if params.ConfigFile is not None:
        config = get_file_from_artifact(s3, in_artifacts.get(params.ConfigArtifact), params.ConfigFile)
    else:
        config = None

    template_url = put_template_into_s3(job_id, params.TemplateFile, json.dumps(template))
    update = stack_exists(cf, params.StackName)
    config = PipelineStackConfig(config, template,
                                 parse_override_params(s3, params.ParameterOverrides, in_artifacts),
                                 update,
                                 params.Capabilities)

    return template_url, config, update


def check_change_set_status(cf, job_id, stack, change_set):
    status = get_change_set_status(cf, stack, change_set)
    if status == 'CREATE_COMPLETE':
        put_job_success(job_id, 'Change set created')
    elif status == 'CREATE_IN_PROGRESS':
        continue_job_later(job_id, 'Change set still in progress')
    else:
        put_job_failure(job_id, 'Change set failed')


def replace_stack_handler(job_id):
    # This operation is not implemented but can be replaced with 2 other operations - delete stack + create stack
    put_job_failure(job_id, 'not implemented')


def delete_stack_handler(job_id, job_data, params: PipelineUserParameters):
    cf = boto3.client('cloudformation')
    if not stack_exists(cf, params.StackName):
        put_job_success(job_id, "Stack do not exist")
        return

    if 'continuationToken' in job_data:
        check_stack_status(cf, job_id, params.StackName)
    else:
        stack_delete(cf, params.StackName, params.RoleArn)
        continue_job_later(job_id, 'Stack create started')


def create_replace_change_set_handler(job_id, job_data, params: PipelineUserParameters, in_artifacts):
    s3, cf = setup_s3_client(job_data), boto3.client('cloudformation')

    if 'continuationToken' in job_data:
        check_change_set_status(cf, job_id, params.StackName, params.ChangeSetName)
    else:
        if change_set_exists(cf, params.StackName, params.ChangeSetName):
            delete_change_set(cf, params.StackName, params.ChangeSetName)

        template_url, config, update = generate_template_and_config(s3, cf, job_id, params, in_artifacts)

        create_change_set(cf, params.StackName, params.ChangeSetName,
                          template_url, config, params.RoleArn)
        continue_job_later(job_id, 'Stack create started')


def execute_change_set_handler(job_id, job_data, params: PipelineUserParameters):
    s3, cf = setup_s3_client(job_data), boto3.client('cloudformation')
    if 'continuationToken' in job_data:
        if check_stack_status(cf, job_id, params.StackName):
            generate_output_artifact(s3, job_data, params, get_stack_output(cf, params.StackName))
    else:
        if not change_set_exists(cf, params.StackName, params.ChangeSetName):
            raise Exception("Change set {} cannot be executed because doesn't exist".format(params.ChangeSetName))
        execute_change_set(cf, params.StackName, params.ChangeSetName)
        continue_job_later(job_id, 'Stack create started')


def create_update_stack_handler(job_id, job_data, params: PipelineUserParameters, in_artifacts):
    s3, cf = setup_s3_client(job_data), boto3.client('cloudformation')

    if 'continuationToken' in job_data:
        if check_stack_status(cf, job_id, params.StackName):
            generate_output_artifact(s3, job_data, params, get_stack_output(cf, params.StackName))
    else:
        template_url, config, update = generate_template_and_config(s3, cf, job_id, params, in_artifacts)
        start_stack_create_or_update(cf, job_id, params.StackName,
                                     template_url, config, update, params.RoleArn)


def handler(event, ctx):
    """ The Lambda Function Handler

    :param event: lambda event
    :param ctx: lambda context
    :return:
    """
    logger.info(event)
    job_id = None
    try:
        job_id = event['CodePipeline.job']['id']
        job_data = event['CodePipeline.job']['data']
        if len(job_data.get('outputArtifacts', [])) > 1:
            raise ValueError("Maximum number of output Artifacts is 1")

        params = PipelineUserParameters(job_data, ctx)
        in_artifacts = load_pipeline_artifacts(job_data.get('inputArtifacts', []), params.Region)

        if params.ActionMode == 'CREATE_UPDATE':
            create_update_stack_handler(job_id, job_data, params, in_artifacts)
        elif params.ActionMode == 'DELETE_ONLY':
            delete_stack_handler(job_id, job_data, params)
        elif params.ActionMode == 'REPLACE_ON_FAILURE':
            replace_stack_handler(job_id)
        elif params.ActionMode == 'CHANGE_SET_REPLACE':
            create_replace_change_set_handler(job_id, job_data, params, in_artifacts)
        elif params.ActionMode == 'CHANGE_SET_EXECUTE':
            execute_change_set_handler(job_id, job_data, params)
        else:
            raise ValueError("Unknown operation mode requested: {}".format(params.ActionMode))

    except Exception as e:
        logger.error('Function failed due to exception. {}'.format(e))
        traceback.print_exc()
        put_job_failure(job_id, 'Function exception: ' + str(e))

    logger.debug('Function complete.')
    return "Complete."
