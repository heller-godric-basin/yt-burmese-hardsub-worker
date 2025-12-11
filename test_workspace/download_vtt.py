import boto3

# Railway S3 configuration
s3_client = boto3.client(
    "s3",
    endpoint_url="https://storage.railway.app",
    aws_access_key_id="tid_lunURdUulOsjnvhOisGsDqLgBuzGuOrrGkPEtTTZtAdMPKMiWl",
    aws_secret_access_key="tsec_kQ8hQsJcBPWrqMZ7mY51ODsXBXWuGpi5V1SppzlkaxQZZbrk_UBYH29MUs5QW4red81gJ8"
)

bucket = "contained-basket-3vehpxma"
key = "storage/polished/GZMqyXbbvjIFduGu.my.vtt"
output_file = "lXfEK8G8CUI.my.vtt"

print(f"Downloading {key} from bucket {bucket}...")
try:
    s3_client.download_file(bucket, key, output_file)
    print(f"Successfully downloaded to {output_file}")
except Exception as e:
    print(f"Error downloading file: {e}")
