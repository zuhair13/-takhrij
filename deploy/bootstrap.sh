#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${1:?Usage: deploy/bootstrap.sh PROJECT_ID [REGION]}"
REGION="${2:-us-central1}"
SERVICE="takhrij"
REPOSITORY="takhrij"
RUNTIME_SA="takhrij-runtime@${PROJECT_ID}.iam.gserviceaccount.com"
PUSH_SA="takhrij-push@${PROJECT_ID}.iam.gserviceaccount.com"
BUILD_SA="takhrij-build@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud config set project "${PROJECT_ID}"
gcloud services enable \
  aiplatform.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  firestore.googleapis.com \
  iam.googleapis.com \
  pubsub.googleapis.com \
  run.googleapis.com

if ! gcloud artifacts repositories describe "${REPOSITORY}" --location="${REGION}" >/dev/null 2>&1; then
  gcloud artifacts repositories create "${REPOSITORY}" \
    --repository-format=docker \
    --location="${REGION}"
fi

if ! gcloud iam service-accounts describe "${RUNTIME_SA}" >/dev/null 2>&1; then
  gcloud iam service-accounts create takhrij-runtime --display-name="TAKHRIJ runtime"
fi
if ! gcloud iam service-accounts describe "${PUSH_SA}" >/dev/null 2>&1; then
  gcloud iam service-accounts create takhrij-push --display-name="TAKHRIJ Pub/Sub push"
fi
if ! gcloud iam service-accounts describe "${BUILD_SA}" >/dev/null 2>&1; then
  gcloud iam service-accounts create takhrij-build --display-name="TAKHRIJ Cloud Build"
fi

for role in roles/aiplatform.user roles/datastore.user roles/pubsub.publisher; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${RUNTIME_SA}" \
    --role="${role}" \
    --condition=None >/dev/null
done

for role in \
  roles/cloudbuild.builds.builder \
  roles/run.admin \
  roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${BUILD_SA}" \
    --role="${role}" \
    --condition=None >/dev/null
done

PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
PUBSUB_AGENT="service-${PROJECT_NUMBER}@gcp-sa-pubsub.iam.gserviceaccount.com"

gcloud iam service-accounts add-iam-policy-binding "${RUNTIME_SA}" \
  --member="serviceAccount:${BUILD_SA}" \
  --role=roles/iam.serviceAccountUser >/dev/null
gcloud iam service-accounts add-iam-policy-binding "${PUSH_SA}" \
  --member="serviceAccount:${PUBSUB_AGENT}" \
  --role=roles/iam.serviceAccountTokenCreator >/dev/null

CURRENT_ACCOUNT="$(gcloud config get-value account 2>/dev/null)"
if [[ "${CURRENT_ACCOUNT}" == *".gserviceaccount.com" ]]; then
  CURRENT_PRINCIPAL="serviceAccount:${CURRENT_ACCOUNT}"
else
  CURRENT_PRINCIPAL="user:${CURRENT_ACCOUNT}"
fi
for service_account in "${BUILD_SA}" "${PUSH_SA}"; do
  gcloud iam service-accounts add-iam-policy-binding "${service_account}" \
    --member="${CURRENT_PRINCIPAL}" \
    --role=roles/iam.serviceAccountUser >/dev/null
done

if ! gcloud firestore databases describe --database='(default)' >/dev/null 2>&1; then
  gcloud firestore databases create --database='(default)' --location="${REGION}" --type=firestore-native
fi

gcloud builds submit \
  --config=deploy/hello-cloudbuild.yaml \
  --service-account="projects/${PROJECT_ID}/serviceAccounts/${BUILD_SA}" \
  --substitutions="_REGION=${REGION},_REPOSITORY=${REPOSITORY},_SERVICE=${SERVICE},_RUNTIME_SERVICE_ACCOUNT=${RUNTIME_SA}" \
  .

SERVICE_URL="$(gcloud run services describe "${SERVICE}" --region="${REGION}" --format='value(status.url)')"
if [[ "$(curl -fsS "${SERVICE_URL}")" != "hello" ]]; then
  echo "Hello deployment did not return the expected body." >&2
  exit 1
fi

printf '%s\n' "Hello deployment verified: ${SERVICE_URL}"
printf '%s\n' "Runtime service account: ${RUNTIME_SA}"
printf '%s\n' "Push service account: ${PUSH_SA}"
printf '%s\n' "Build service account: ${BUILD_SA}"
