import json
import os
from pathlib import Path

from google.cloud import storage
from google.oauth2 import service_account

SECRET_KEY = "APPS_CDN_SERVICE_ACCOUNT_CREDENTIALS"
BUCKET_NAME = "apps-cdn-bucket-cognitedata-production"
LOCAL_DIR = "data"
DEST_PREFIX = "toolkit"
SOURCE_DIR = "data"


def authenticate_with_service_account(credentials_json: str):
    # Parse the JSON string into a dictionary
    credentials_dict = json.loads(credentials_json)

    # Create credentials object from the parsed dictionary
    credentials = service_account.Credentials.from_service_account_info(
        credentials_dict
    )

    # Initialize the Storage client with the credentials
    return storage.Client(credentials=credentials)


def sync_local_to_gcs(local_dir: str, dest_prefix: str):
    local_path = Path(local_dir)

    if not local_path.is_dir():
        print(f"Error: {local_dir} is not a valid directory.")
        return

    credentials_json = os.environ.get(SECRET_KEY)
    if not credentials_json:
        raise ValueError(f"{SECRET_KEY} not set in the environment.")

    # Authenticate and initialize the client
    client = authenticate_with_service_account(credentials_json)
    bucket = client.bucket(BUCKET_NAME)

    # Traverse through all files in the local directory
    for source in local_path.rglob("*"):
        if source.is_file():  # Only process files
            destination = Path(dest_prefix) / source.relative_to(local_path)
            blob = bucket.blob(str(destination))
            if blob.exists():
                print(
                    f"Skipping {source}, already exists in bucket as {destination!s}."
                )
                continue
            print(f"Uploading {source} to {destination!s}...")
            blob.upload_from_filename(str(source))


if __name__ == "__main__":
    sync_local_to_gcs(LOCAL_DIR, DEST_PREFIX)
