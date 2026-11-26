# SubGuard AI Deployment Guide (Google Cloud Run)

Replace `PROJECT_ID` and `REGION` (e.g., `asia-south1` or `us-central1`) with your team's values.

## 1. Enable APIs & Create Firestore Database
1. In Google Cloud Console → **APIs & Services → Library**, enable:
   - Gmail API (`gmail.googleapis.com`)
   - Cloud Run Admin API (`run.googleapis.com`)
   - Cloud Build API (`cloudbuild.googleapis.com`)
   - Artifact Registry API (`artifactregistry.googleapis.com`)
   - Cloud Firestore API (`firestore.googleapis.com`)
   - Secret Manager API (`secretmanager.googleapis.com`)
   - Cloud Scheduler API (`cloudscheduler.googleapis.com`)
2. In **Firestore**, create one **Native mode** database in your chosen region.

## 2. Deploy the Web Service (`subguard-web`)
```bash
gcloud config set project PROJECT_ID
gcloud run deploy subguard-web \
  --source . \
  --region REGION \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 2 \
  --set-env-vars SERVICE_MODE=web,GOOGLE_CLOUD_PROJECT=PROJECT_ID,GEMINI_MODEL=gemini-2.5-flash
```
After deployment, copy the `https://...` URL, set `APP_BASE_URL` on `subguard-web` to that URL, and register `https://YOUR_DEPLOYED_HOST/auth/google/callback` in **Google Auth Platform → Clients**.

## 3. Secrets in Secret Manager
Store `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `SESSION_SECRET`, `TOKEN_ENCRYPTION_KEY`, and `GOOGLE_API_KEY` in **Secret Manager** and bind them as environment variables on `subguard-web` (and `SESSION_SECRET` / `TOKEN_ENCRYPTION_KEY` if needed on `subguard-worker`).

## 4. Deploy the Private Worker Service (`subguard-worker`)
```bash
gcloud run deploy subguard-worker \
  --source . \
  --region REGION \
  --no-allow-unauthenticated \
  --min-instances 0 \
  --max-instances 1 \
  --set-env-vars SERVICE_MODE=worker,GOOGLE_CLOUD_PROJECT=PROJECT_ID
```

## 5. Cloud Scheduler Job (1-minute delivery)
1. Create a dedicated calling service account and grant it `roles/run.invoker` on `subguard-worker`.
2. In **Cloud Scheduler**, create a job:
   - Frequency: `* * * * *`
   - Target type: **HTTP**
   - URL: `https://YOUR_WORKER_URL/jobs/deliver`
   - HTTP method: **POST**
   - Auth header: **Add OIDC token**
   - Service account: your calling service account
   - Audience: `https://YOUR_WORKER_URL`
