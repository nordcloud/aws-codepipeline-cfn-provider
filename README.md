# aws-codepipeline-cfn-provider

aws-codepipeline-cfn-provider is a lambda that works very similar to codepipeline build in cfn provider.
However it uploads template to s3 bucket before creating stack so it can be used to deploy stacks > 51k.

## Deployment
TODO

## UserParameters
User parameters are used to configure lambda and should be passed in JSON format
```
{
    "Operation": "operation_name", [CREATE_UPDATE_STACK, DELETE_STACK, CREATE_REPLACE_CHANGE_SET, EXECUTE_CHANGE_SET]
    "StackName": "stack_name",
    "ChangeSetName": "change_set_name",
    "Template": "ArtifactName::TemplateFile",
    "Config": "ArtifactName::ConfigFile",
    "RoleName": "role_name_to_execute_cfn_template",
    "OutputFileName": "artifact_output_file_name" (output.json is default),
    "ParametersOverride": {"param": "value"}
}
```

## Lambda environment
- PIPELINE_TEMPLATES_BUCKET - stack name used to upload cfn templates

## Examples

#### Delete stack:
```
{
    "Operation": "DELETE_STACK",
    "StackName": "test_stack",
    "RoleName": "cfn_role"
}
```

#### Create or update stack:
```
{
    "Operation": "CREATE_UPDATE_STACK",
    "StackName": "test_stack",
    "RoleName": "cfn_role",
    "Template": "MyApp::template.json",
    "Config": "MyApp::config.json",
    "ParametersOverride": {
        "param1": "value1",
        "param2": { "Fn::GetParam" : [ "MyApp", "config2.json", "param2" ] }
    }
}
```

#### Create change set:
```
{
    "Operation": "CREATE_REPLACE_CHANGE_SET",
    "StackName": "test_stack",
    "ChangeSetName": "test_change_set",
    "RoleName": "cfn_role",
    "Template": "MyApp::template.json",
    "Config": "MyApp::config.json",
    "ParametersOverride": {
        "param1": "value1",
        "param2": { "Fn::GetParam" : [ "MyApp", "config2.json", "param2" ] }
    }
}
```

#### Execute change set:
```
{
    "Operation": "EXECUTE_CHANGE_SET",
    "StackName": "test_stack",
    "ChangeSetName": "test_change_set",
    "RoleName": "cfn_role"
    "OutputFileName": "out.json"
}
```