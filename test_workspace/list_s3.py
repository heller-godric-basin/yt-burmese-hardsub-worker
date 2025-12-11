import boto3

# Railway S3 configuration
s3_client = boto3.client(
    "s3",
    endpoint_url="https://storage.railway.app",
    aws_access_key_id="tid_lunURdUulOsjnvhOisGsDqLgBuzGuOrrGkPEtTTZtAdMPKMiWl",
    aws_secret_access_key="tsec_kQ8hQsJcBPWrqMZ7mY51ODsXBXWuGpi5V1SppzlkaxQZZbrk_UBYH29MUs5QW4red81gJ8"
)

bucket = "contained-basket-3vehpxma"

print(f"Listing objects in bucket {bucket}...")
try:
    paginator = s3_client.get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=bucket, Prefix="storage/polished/"):
        if 'Contents' in page:
            for obj in page['Contents']:
                print(f"  {obj['Key']}")
        else:
            print("No objects found")
except Exception as e:
    print(f"Error listing bucket: {e}")
