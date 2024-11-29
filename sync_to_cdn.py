

import json
import os
from google.cloud import storage
from google.oauth2 import service_account

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
    credentials = service_account.Credentials.from_service_account_info(credentials_dict)

    # Initialize the Storage client with the credentials
    return storage.Client(credentials=credentials)


if __name__ == "__main__":
    # Load the service account credentials from secrets (replace with actual loading logic)

    SECRET_KEY = "APPS_CDN_SERVICE_ACCOUNT_CREDENTIALS"
    BUCKET_NAME="apps-cdn-bucket-cognitedata-production"
    DEST_PREFIX="toolkit"
    SOURCE_DIR="data"

    
    credentials_json = os.environ.get(SECRET_KEY)
    if not credentials_json:
        raise ValueError(f"{SECRET_KEY} not set in the environment.")

    # Authenticate and initialize the client
    client = authenticate_with_service_account(credentials_json)

    bucket = client.bucket(BUCKET_NAME)
    blobs = bucket.list_blobs(prefix=DEST_PREFIX)
    for blob in blobs:
        print(blob.name)
