#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${1:?Usage: deploy/configure_pubsub.sh PROJECT_ID [REGION]}"
REGION="${2:-us-central1}"
SERVICE="takhrij"
TOPIC="takhrij-claims"
DLQ_TOPIC="takhrij-claims-dead-letter"
SUBSCRIPTION="takhrij-worker-push"
PUSH_SA="takhrij-push@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud config set project "${PROJECT_ID}"
PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
PUBSUB_AGENT="service-${PROJECT_NUMBER}@gcp-sa-pubsub.iam.gserviceaccount.com"
SERVICE_URL="$(gcloud run services describe "${SERVICE}" --region="${REGION}" --format='value(status.url)')"
WORKER_URL="${SERVICE_URL}/worker"

gcloud pubsub topics describe "${TOPIC}" >/dev/null 2>&1 || gcloud pubsub topics create "${TOPIC}"
gcloud pubsub topics describe "${DLQ_TOPIC}" >/dev/null 2>&1 || gcloud pubsub topics create "${DLQ_TOPIC}"

gcloud run services add-iam-policy-binding "${SERVICE}" \
  --region="${REGION}" \
  --member="serviceAccount:${PUSH_SA}" \
  --role=roles/run.invoker >/dev/null

if gcloud pubsub subscriptions describe "${SUBSCRIPTION}" >/dev/null 2>&1; then
  gcloud pubsub subscriptions update "${SUBSCRIPTION}" \
    --push-endpoint="${WORKER_URL}" \
    --push-auth-service-account="${PUSH_SA}" \
    --push-auth-token-audience="${WORKER_URL}" \
    --ack-deadline=600 \
    --dead-letter-topic="${DLQ_TOPIC}" \
    --max-delivery-attempts=5
else
  gcloud pubsub subscriptions create "${SUBSCRIPTION}" \
    --topic="${TOPIC}" \
    --push-endpoint="${WORKER_URL}" \
    --push-auth-service-account="${PUSH_SA}" \
    --push-auth-token-audience="${WORKER_URL}" \
    --ack-deadline=600 \
    --dead-letter-topic="${DLQ_TOPIC}" \
    --max-delivery-attempts=5
fi

gcloud pubsub topics add-iam-policy-binding "${DLQ_TOPIC}" \
  --member="serviceAccount:${PUBSUB_AGENT}" \
  --role=roles/pubsub.publisher >/dev/null
gcloud pubsub subscriptions add-iam-policy-binding "${SUBSCRIPTION}" \
  --member="serviceAccount:${PUBSUB_AGENT}" \
  --role=roles/pubsub.subscriber >/dev/null

gcloud run services update "${SERVICE}" \
  --region="${REGION}" \
  --update-env-vars="PUBSUB_AUDIENCE=${WORKER_URL},PUBSUB_SERVICE_ACCOUNT=${PUSH_SA}" >/dev/null

printf '%s\n' "Push subscription configured for ${WORKER_URL}"
