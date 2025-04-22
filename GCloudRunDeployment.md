# Google Cloud Run Deployment Plan for YouTube Clipping Service

This document outlines the steps required to deploy the Flask-based YouTube Clipping Service to Google Cloud Run.

**Last Updated:** 2025-04-22

**Selected GCP Region:** `asia-southeast1` (Singapore)

## 1. Prerequisites

1.  **Google Cloud Project:** Ensure you have a Google Cloud project set up. Note the Project ID.
2.  **Billing Enabled:** Ensure billing is enabled for your project.
3.  **`gcloud` CLI:** Install and configure the [Google Cloud CLI](https://cloud.google.com/sdk/docs/install). Authenticate with `gcloud auth login` and set your project with `gcloud config set project YOUR_PROJECT_ID`.
4.  **Enable APIs:** Enable the following APIs in your Google Cloud project:
    *   Cloud Run API (`run.googleapis.com`)
    *   Artifact Registry API (`artifactregistry.googleapis.com`)
    *   Cloud Storage API (`storage.googleapis.com`)
    *   Secret Manager API (`secretmanager.googleapis.com`) (Recommended for secrets)
    *   (Optional) Cloud SQL Admin API / Firestore API if using a database for state.

## 2. Code & Configuration Modifications

Significant changes are needed to make the application suitable for the stateless environment of Cloud Run.

1.  **Dockerfile Adjustments (`Dockerfile`):**
    *   **Replace `CMD`:** Change the `CMD` from `["flask", "run", "--no-debugger", "--reload"]` to use a production-grade WSGI server like Gunicorn. Gunicorn needs to be added to `requirements.txt`.
        *   Add `gunicorn` to `requirements.txt`.
        *   Update `Dockerfile` `RUN pip install...` command.
        *   Change `CMD` to something like: `CMD ["gunicorn", "--bind", "0.0.0.0:$PORT", "--workers", "4", "src.server:app"]`
            *   `$PORT`: Cloud Run injects this environment variable. Gunicorn must listen on this port.
            *   `--workers`: Adjust based on performance testing and Cloud Run instance CPU/memory.
    *   **Remove `FLASK_RUN_PORT` Env Var:** The `FLASK_RUN_PORT=5000` environment variable set in the Dockerfile is no longer needed if using Gunicorn listening on `$PORT`.
    *   **_Status: COMPLETED_**
        *   _`gunicorn` added to `requirements.txt`._
        *   _`Dockerfile` updated to install `gunicorn` and use `CMD ["gunicorn", "--bind", "0.0.0.0:$PORT", "--timeout", "300", "src.server:app"]`._

2.  **Configuration Management (`config.py`):**
    *   Modify the application to read configuration primarily from **environment variables** instead of hardcoding paths in `config.py`.
    *   Examples: `DOWNLOAD_BUCKET`, `TASKS_OBJECT`, `KEYS_OBJECT`, `MAX_WORKERS`, `COOKIE_SECRET_VERSION`.
    *   Keep `config.py` for defaults if an environment variable isn't set, but prioritize environment variables.
    *   **_Status: COMPLETED_**
        *   _`config.py` updated to use `os.environ.get()` for Cloud Run specific variables (`STATE_BUCKET`, `TASKS_OBJECT_PATH`, `KEYS_OBJECT_PATH`, `DOWNLOAD_BUCKET`, `COOKIE_SECRET_VERSION`), retaining original values as defaults._

3.  **State Persistence (Critical):**
    *   **Replace JSON Files:** `jsons/tasks.json` and `jsons/api_keys.json` cannot be stored reliably on the local filesystem.
        *   **Option A (Recommended): Google Cloud Storage (GCS):**
            *   Modify `src/json_utils.py` (or equivalent logic) to read/write these files from/to specific objects within a GCS bucket.
            *   Use the `google-cloud-storage` Python library (add to `requirements.txt`).
            *   Implement locking mechanisms if concurrent writes are possible (e.g., using GCS object generation preconditions).
            *   Pass the GCS bucket name and object paths via environment variables (e.g., `STATE_BUCKET`, `TASKS_OBJECT_PATH`, `KEYS_OBJECT_PATH`).
        *   **Option B: Database (Cloud SQL/Firestore):**
            *   A more robust solution, especially for managing API keys and task states.
            *   Requires more significant code changes to replace JSON file logic with database interactions (e.g., using SQLAlchemy for Cloud SQL or `google-cloud-firestore` library).
            *   Store database connection details securely (see Secret Management).
    *   **Replace Local Downloads:** Files downloaded to `/app/downloads` will be lost.
        *   Modify `src/yt_handler.py` (or equivalent logic) to upload completed downloads directly to a **GCS bucket**.
        *   Use the `google-cloud-storage` library.
        *   Pass the destination GCS bucket name via an environment variable (e.g., `DOWNLOAD_BUCKET`).
        *   Modify the `/files/<path:filename>` endpoint (`src/server.py`) to:
            *   No longer serve files directly from the local filesystem.
            *   Instead, generate a **signed URL** for the requested object in the GCS bucket and redirect the user or return the signed URL.
            *   Ensure the Cloud Run service account has permissions to generate signed URLs.
    *   **_Status: COMPLETED (using Option 3A - GCS)_**
        *   _`src/json_utils.py` modified to use `google-cloud-storage` for loading/saving tasks and keys based on `STATE_BUCKET` environment variable._
        *   _`src/yt_handler.py` modified to upload downloaded files to `DOWNLOAD_BUCKET` and update task status with GCS paths._
        *   _`src/server.py`'s `/files/` endpoint modified to check `USE_GCS_DOWNLOADS` flag (derived from `DOWNLOAD_BUCKET` in `config.py`) and generate/redirect to signed URLs if enabled._

4.  **Cookie Management (`youtube_cookies.txt`):**
    *   **Option A (Recommended): Secret Manager:**
        *   Store the content of `youtube_cookies.txt` as a secret in Google Secret Manager.
        *   Modify the application startup logic (e.g., in `src/server.py` or `src/yt_handler.py`) to fetch the secret value using the `google-cloud-secret-manager` library (add to `requirements.txt`).
        *   Write the fetched content to a temporary file location accessible by `yt-dlp` within the container (e.g., `/tmp/youtube_cookies.txt`) or configure `yt-dlp` to use the secret directly if possible.
        *   Pass the Secret Manager secret version name via an environment variable (e.g., `COOKIE_SECRET_VERSION`).
    *   **Option B: GCS:** Store the file in a GCS bucket and download it at container startup. Requires careful permissions management.
    *   **_Status: COMPLETED (using Option 4A - Secret Manager)_**
        *   _`src/yt_handler.py` modified to use `google-cloud-secret-manager` to fetch cookie data based on `COOKIE_SECRET_VERSION` environment variable and provide it to `yt-dlp` via a temporary file._

5.  **Dependencies (`requirements.txt`):**
    *   Add `gunicorn`.
    *   Add `google-cloud-storage`.
    *   Add `google-cloud-secret-manager` (if using Option 4A).
    *   Add relevant database libraries if using Option 3B.
    *   **_Status: COMPLETED_**
        *   _`requirements.txt` updated with `gunicorn`, `google-cloud-storage`, and `google-cloud-secret-manager`._

## 3. Google Cloud Infrastructure Setup

1.  **Artifact Registry:** Create a Docker repository.
    *   `gcloud artifacts repositories create youtube-clipping-service --repository-format=docker --location=asia-southeast1 --description="Docker images for YouTube Clipping Service"`
    *   Note the full repository path (e.g., `asia-southeast1-docker.pkg.dev/YOUR_PROJECT_ID/youtube-clipping-service`).
2.  **Cloud Storage:** Create GCS bucket(s).
    *   **Bucket for State (if using GCS for JSON):** `gs://your-project-id-yt-state`
    *   **Bucket for Downloads:** `gs://your-project-id-yt-downloads`
    *   Configure appropriate permissions (e.g., grant the Cloud Run service account Storage Object Admin/Creator roles).
3.  **Secret Manager (if used):**
    *   Create secrets for sensitive data (e.g., `youtube-cookie-data`).
    *   Grant the Cloud Run service account the "Secret Manager Secret Accessor" role for the specific secrets.
4.  **(Optional) Database:** Set up Cloud SQL instance or Firestore database if chosen. Configure users, passwords, and networking. Store credentials securely (Secret Manager).

## 4. Build and Push Docker Image

1.  **Authenticate Docker:** Configure Docker to authenticate with Artifact Registry:
    *   `gcloud auth configure-docker asia-southeast1-docker.pkg.dev`
2.  **Build:** Navigate to your project root directory (containing the `Dockerfile`).
    *   `docker build -t asia-southeast1-docker.pkg.dev/YOUR_PROJECT_ID/youtube-clipping-service/yt-clip-service:latest .`
3.  **Push:**
    *   `docker push asia-southeast1-docker.pkg.dev/YOUR_PROJECT_ID/youtube-clipping-service/yt-clip-service:latest`

## 5. Deploy to Cloud Run

1.  **Initial Deployment:** Use the `gcloud run deploy` command. Replace placeholders.
    ```bash
    gcloud run deploy yt-clip-service \
        --image asia-southeast1-docker.pkg.dev/YOUR_PROJECT_ID/youtube-clipping-service/yt-clip-service:latest \
        --region asia-southeast1 \
        --allow-unauthenticated \ # Or configure IAM for authentication
        --set-env-vars="STATE_BUCKET=gs://your-project-id-yt-state" \
        --set-env-vars="TASKS_OBJECT_PATH=tasks.json" \
        --set-env-vars="KEYS_OBJECT_PATH=api_keys.json" \
        --set-env-vars="DOWNLOAD_BUCKET=gs://your-project-id-yt-downloads" \
        --set-env-vars="COOKIE_SECRET_VERSION=projects/YOUR_PROJECT_ID/secrets/youtube-cookie-data/versions/latest" \ # Example
        --set-env-vars="MAX_WORKERS=4" \ # Adjust as needed
        --memory=2Gi \ # Adjust based on testing
        --cpu=1 \ # Adjust based on testing
        --concurrency=10 \ # Adjust based on task duration and type
        --timeout=600 \ # Set appropriate request timeout (max 3600s)
        --service-account=YOUR_SERVICE_ACCOUNT_EMAIL # Optional: Use a specific service account
        # Add database connection env vars if needed
    ```
2.  **Service Account Permissions:** Ensure the Cloud Run service account (either the default Compute Engine service account or a dedicated one specified with `--service-account`) has the necessary IAM roles:
    *   `roles/storage.objectAdmin` on the state and download GCS buckets.
    *   `roles/secretmanager.secretAccessor` on the secrets used.
    *   `roles/cloudsql.client` (if using Cloud SQL).
    *   `roles/datastore.user` (if using Firestore).
3.  **Updates:** For subsequent deployments, simply re-run the `gcloud run deploy ...` command after pushing a new image tag.

## 6. Testing

1.  Obtain the URL provided by Cloud Run after deployment.
2.  Test all API endpoints using `curl` or a tool like Postman.
3.  Verify that tasks are created and state is persisted (check GCS objects or database).
4.  Verify that downloads complete successfully and are stored in the GCS download bucket.
5.  Verify that the `/files/` endpoint correctly provides access to downloaded files (e.g., via signed URLs).
6.  Monitor logs in Cloud Logging for errors.

## 7. CI/CD (Optional but Recommended)

*   Set up Cloud Build triggers to automatically build the Docker image and deploy to Cloud Run upon commits to your Git repository (e.g., `main` branch).
