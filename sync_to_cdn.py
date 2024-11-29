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
    """
    Authenticate using a service account JSON key.

    Args:
        credentials_json (str): The JSON string for the service account credentials.

    Returns:
        google.cloud.storage.Client: Authenticated GCS client.
    """
    # Parse the JSON string into a dictionary
    credentials_dict = json.loads(credentials_json)

    # Create credentials object from the parsed dictionary
    credentials = service_account.Credentials.from_service_account_info(
        credentials_dict
    )

    # Initialize the Storage client with the credentials
    return storage.Client(credentials=credentials)


def upload_file(file_path: Path, dest_prefix: str, client: storage.Client):
    # Construct the destination path in GCS
    relative_path = file_path.relative_to(
        file_path.parents[1]
    )  # Adjust relative path logic if needed
    blob_name = f"{dest_prefix}/{relative_path}"

    bucket = client.bucket(BUCKET_NAME)
    blob = bucket.blob(blob_name)

    # Check if the file already exists in GCS
    if blob.exists():
        print(f"Skipping {file_path}, already exists in bucket as {blob_name}.")
        return

    # Upload the file
    print(f"Uploading {file_path} to {blob_name}...")
    blob.upload_from_filename(str(file_path))


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

    # Traverse through all files in the local directory
    for file_path in local_path.rglob("*"):
        if file_path.is_file():  # Only process files
            upload_file(file_path, dest_prefix, client)


if __name__ == "__main__":
    sync_local_to_gcs(LOCAL_DIR, DEST_PREFIX)
