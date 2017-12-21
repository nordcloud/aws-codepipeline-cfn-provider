import json

from botocore.exceptions import ClientError

from utils.logging_utils import get_logger
from utils.pipeline_utils import PipelineStackConfig

logger = get_logger()


def get_stack_output(cf, stack_name):
    """Return dict with stack outputs

    :param cf: cfn client
    :param stack_name: stack name to describe
    :return: dict with parameters
    """
    stack_details = cf.describe_stacks(StackName=stack_name)
    output_params = stack_details['Stacks'][0].get('Outputs', [])
    outputs = {}
    logger.info(output_params)
    for op in output_params:
        outputs[op['OutputKey']] = op['OutputValue']
    return outputs


def stack_delete(cf, stack, role_arn=None):
    """Deletes stack

    :param cf: cfn client
    :param stack: stack name to delete
    :param role_arn: role name to be assumed by cfn
    """
    kwargs = {}
    if role_arn is not None:
        kwargs['RoleARN'] = role_arn

    cf.delete_stack(StackName=stack, **kwargs)


def stack_exists(cf, stack):
    """Check if a stack exists or not

    :param cf: cfn client
    :param stack: stack name t ocheck
    :return: True or false
    """
    try:
        cf.describe_stacks(StackName=stack)
        return True
    except ClientError as e:
        if "does not exist" in e.response['Error']['Message']:
            return False
        else:
            raise e


def create_stack(cf, stack, template_url, config: PipelineStackConfig, role_arn=None):
    """Starts a new CloudFormation stack creation

    :param cf: cfn template
    :param stack:  stack name to create
    :param template_url: s3 url with template
    :param config: Obj with tags, parameters and stack policy
    :param role_arn: role to be assumed by cfn
    """
    logger.debug("create_stack " + template_url)

    kwargs = {}
    if config.StackPolicy is not None:
        kwargs['StackPolicyBody'] = json.dumps(config.StackPolicy)
    if role_arn is not None:
        kwargs['RoleARN'] = role_arn
    if config.Capabilities is not None:
        kwargs['Capabilities'] = config.Capabilities if type(config.Capabilities) is list else [config.Capabilities]

    cf.create_stack(
        StackName=stack,
        TemplateURL=template_url,
        Parameters=config.Parameters,
        Tags=config.Tags,
        **kwargs)


def update_stack(cf, stack, template_url, config: PipelineStackConfig, role_arn=None):
    """Start a CloudFormation stack update

    :param cf: cfn template
    :param stack:  stack name to update
    :param template_url: s3 url with template
    :param config: Obj with tags, parameters and stack policy
    :param role_arn: role to be assumed by cfn
    """
    try:
        kwargs = {}
        if config.StackPolicy is not None:
            kwargs['StackPolicyBody'] = json.dumps(config.StackPolicy)
        if role_arn is not None:
            kwargs['RoleARN'] = role_arn
        if config.Capabilities is not None:
            kwargs['Capabilities'] = config.Capabilities if type(config.Capabilities) is list else [config.Capabilities]

        cf.update_stack(
            StackName=stack,
            TemplateURL=template_url,
            Parameters=config.Parameters,
            Tags=config.Tags,
            **kwargs)
        return True
    except ClientError as e:
        if e.response['Error']['Message'] == 'No updates are to be performed.':
            return False
        else:
            raise Exception('Error updating CloudFormation stack {} {}'.format(stack, str(e)))


def get_stack_status(cf, stack):
    """Get the status of an existing CloudFormation stack

    :param cf: cfn client
    :param stack: stack name to describe
    :return: status
    """
    logger.debug("get_stack_status")
    stack_description = cf.describe_stacks(StackName=stack)
    return stack_description['Stacks'][0]['StackStatus']


def change_set_exists(cf, stack, change_set):
    """Check if a CFN change_set exists or not

    :param cf: cfn client
    :param stack: stack name to check
    :param change_set: change set name to check
    :return: True or False
    """
    try:
        cf.describe_change_set(ChangeSetName=change_set, StackName=stack)
        return True
    except ClientError as e:
        if "does not exist" in e.response['Error']['Message']:
            return False
        else:
            raise e


def create_change_set(cf, cfn_stack_name, cfn_change_set_name, template_url,
                      config: PipelineStackConfig, role_arn=None):
    """Creates new change set

    :param cf: cfn client
    :param cfn_stack_name: stack name
    :param cfn_change_set_name: change set name
    :param template_url: s3 url with template file
    :param config: config object with parameters, tags etc
    :param role_arn: role arn to be used by cfn
    """
    logger.debug("create_change-set, template: " + template_url)
    change_set_type = 'UPDATE' if config.Update is True else 'CREATE'

    kwargs = {}
    if role_arn is not None:
        kwargs['RoleARN'] = role_arn
    if config.Capabilities is not None:
        kwargs['Capabilities'] = config.Capabilities if type(config.Capabilities) is list else [config.Capabilities]

    cf.create_change_set(
        StackName=cfn_stack_name,
        ChangeSetName=cfn_change_set_name,
        TemplateURL=template_url,
        Parameters=config.Parameters,
        ChangeSetType=change_set_type,
        **kwargs)


def execute_change_set(cf, cfn_stack_name, cfn_change_set_name):
    """Execute existing change set

    :param cf: cfn client
    :param cfn_stack_name: stack name
    :param cfn_change_set_name: change set name

    """
    logger.debug("execute_change_set")
    cf.execute_change_set(StackName=cfn_stack_name, ChangeSetName=cfn_change_set_name)


def get_change_set_status(cf, cfn_stack_name, cfn_change_set_name):
    """Returns change set status

    :param cf: cfn client
    :param cfn_stack_name: stack name
    :param cfn_change_set_name: chenge set name
    :return: status
    """
    details = cf.describe_change_set(ChangeSetName=cfn_change_set_name, StackName=cfn_stack_name)
    return details['Status']


def delete_change_set(cf, cfn_stack_name, cfn_change_set_name):
    """Deletes change set

    :param cf: cfn client
    :param cfn_stack_name: stack name
    :param cfn_change_set_name: change set name
    """
    cf.delete_change_set(ChangeSetName=cfn_change_set_name, StackName=cfn_stack_name)
