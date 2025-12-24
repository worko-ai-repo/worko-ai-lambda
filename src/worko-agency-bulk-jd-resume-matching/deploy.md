#add triger from s3
Source: S3
Bucket: worko-app-dev
request type : put
Prefix: agencies/
Suffix: .pdf
Events: All object create events