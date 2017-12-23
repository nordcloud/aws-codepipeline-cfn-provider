# aws-codepipeline-cfn-provider

[![Lintly](https://lintly.com/gh/nordcloud/aws-codepipeline-cfn-provider/badge.svg)](https://lintly.com/gh/nordcloud/aws-codepipeline-cfn-provider/)


CodePipeline built-in cfn provider has a limitation that a cfn template size can't exceed 51kb. 

`aws-codepipeline-cfn-provider` solves this problem by providing an alternative cfn provider implemented as a Lambda. 

Instead of passing templates directly, it uploads templates to s3 bucket before creating a stack so it can be used to deploy stacks from templates with size > 51kb.

## Requirements
Lambda requires an s3 bucket used to store cfn templates.
The bucket name is set by `PIPELINE_TEMPLATES_BUCKET` environment variable.

## Deployment

aws-codepipeline-cfn-provider uses `Pipenv` to manage Python dependencies.

#### Create virtualenv and install dependencies
```
pipenv --three
pipenv install
```


#### Upload zip to an S3 bucket
Modify bucket name and bucket key in `s3_deploy.sh` script
Run `s3_deploy.sh` to generate a zip package and upload file to S3 bucket.

#### Lambda
Create a Lambda in AWS console using zipped package from s3 bucket.
Lambda handler name should be set to: `pipeline_lambda/pipeline_lambda.handler`

## IAM permissions
aws-codepipeline-cfn-provider requires at least the following permissions:
```
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Action": [
                "codepipeline:PutJobFailureResult",
                "codepipeline:PutJobSuccessResult"
            ],
            "Resource": "*",
            "Effect": "Allow"
        },
        {
            "Action": [
                "cloudformation:DescribeStacks",
                "cloudformation:DeleteStack",
                "cloudformation:CreateStack",
                "cloudformation:UpdateStack",
                "cloudformation:DescribeChangeSet",
                "cloudformation:CreateChangeSet",
                "cloudformation:ExecuteChangeSet",
                "cloudformation:SetStackPolicy",
                "cloudformation:DeleteChangeSet",
                "iam:PassRole"
            ],
            "Resource": "*",
            "Effect": "Allow"
        },
        {
            "Action": [
                "s3:GetObject",
                "s3:PutObject"
            ],
            "Resource": [
                "arn:aws:s3:::your-pipeline-templates-bucket/*"
            ],
            "Effect": "Allow"
        },
        {
            "Action": [
                "s3:GetBucketLocation"
            ],
            "Resource": [
                "arn:aws:s3:::your-pipeline-templates-bucket"
            ],
            "Effect": "Allow"
        }
    ]
}

```

## UserParameters
User parameters are used to configure lambda and should be passed in a JSON format:

```
{
    "ActionMode": "operation_name", [CREATE_UPDATE, DELETE_ONLY, CHANGE_SET_REPLACE, CHANGE_SET_EXECUTE]
    "StackName": "stack_name",
    "ChangeSetName": "change_set_name",
    "TemplatePath": "ArtifactName::TemplateFile",
    "ConfigPath": "ArtifactName::ConfigFile",
    "RoleArn": "cfn_role_arn",
    "OutputFileName": "artifact_output_file_name" (output.json is default),
    "ParameterOverrides": {"param": "value"}
    "Capabilities": ["CAPABILITY_NAMED_IAM", "CAPABILITY_IAM"] list or string
}
```

## Lambda environment
- `PIPELINE_TEMPLATES_BUCKET` - S3 bucket used to upload cfn templates to

## Examples

### Pipeline examples
#### Create stack
![pipeline create stack example](https://s3.eu-central-1.amazonaws.com/nordcloud-rnd-github-src/nc_pipeline_1.png)

#### Create and execute change set with manual approvement
![pipeline change set example](https://s3.eu-central-1.amazonaws.com/nordcloud-rnd-github-src/nc_pipeline_2.png)

### Configuration examples
#### Delete stack:
```
{
    "StackName": "test_stack",
    "ActionMode": "DELETE_ONLY,
    "RoleArn": "cfn_role_arn",

}
```

#### Create or update stack:
```
{
    "ActionMode": "CREATE_UPDATE",
    "StackName": "test_stack",
    "RoleArn": "cfn_role_arn",
    "TemplatePath": "MyApp::template.json",
    "ConfigPath": "MyApp::config.json",
    "ParameterOverrides": {
        "param1": "value1",
        "param2": { "Fn::GetParam" : [ "MyApp", "config2.json", "param2" ] }
    }
}
```

#### Create change set:
```
{
    "ActionMode": "CHANGE_SET_REPLACE",
    "StackName": "test_stack",
    "ChangeSetName": "test_change_set",
    "RoleArn": "cfn_role_arn",
    "TemplatePath": "MyApp::template.json",
    "ConfigPath": "MyApp::config.json",
    "ParameterOverrides": {
        "param1": "value1",
        "param2": { "Fn::GetParam" : [ "MyApp", "config2.json", "param2" ] }
    }
}
```

#### Execute change set:
```
{
    "ActionMode": "CHANGE_SET_EXECUTE",
    "StackName": "test_stack",
    "ChangeSetName": "test_change_set",
    "RoleArn": "cfn_role_arn"
    "OutputFileName": "out.json"
}
```

## LICENCE 

Apache License 2.0

Copyright Nordcloud OY
