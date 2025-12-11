import boto3
import sys

# Railway S3 configuration
s3_client = boto3.client(
    "s3",
    endpoint_url="https://storage.railway.app",
    aws_access_key_id="tid_lunURdUulOsjnvhOisGsDqLgBuzGuOrrGkPEtTTZtAdMPKMiWl",
    aws_secret_access_key="tsec_kQ8hQsJcBPWrqMZ7mY51ODsXBXWuGpi5V1SppzlkaxQZZbrk_UBYH29MUs5QW4red81gJ8"
)

bucket = "contained-basket-3vehpxma"
local_file = "lXfEK8G8CUI_hardsubbed_test.mp4"
s3_key = "storage/hard-subbed/lXfEK8G8CUI_test.mp4"

print(f"Uploading {local_file} to s3://{bucket}/{s3_key}...")
try:
    s3_client.upload_file(local_file, bucket, s3_key)
    print(f"✓ Successfully uploaded to s3://{bucket}/{s3_key}")
except Exception as e:
    print(f"Error uploading file: {e}")
    sys.exit(1)
