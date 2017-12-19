BUCKET_NAME="aws-codepipeline-cfn-provider-bucket"
BUCKET_KEY="pipeline_lambda.zip"

mkdir build
cp -r $VIRTUAL_ENV/lib/python3.6/site-packages/* build/
cp -r utils build/
cp -r pipeline_lambda build/
cd build
zip -r pipeline_lambda.zip *
aws s3 cp pipeline_lambda.zip s3://$BUCKET_NAME/$BUCKET_KEY
cd ..
rm -rf build