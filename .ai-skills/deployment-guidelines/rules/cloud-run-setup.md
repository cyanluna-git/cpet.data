# Google Cloud Run - FastAPI Container

## Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app

ENV PYTHONUNBUFFERED=1
ENV PORT=8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

## cloud-run-deploy.sh

```bash
#!/bin/bash
PROJECT_ID="your-gcp-project"
SERVICE_NAME="cpet-db-backend"
REGION="us-central1"

cd backend

gcloud builds submit --tag gcr.io/$PROJECT_ID/$SERVICE_NAME

gcloud run deploy $SERVICE_NAME \
  --image gcr.io/$PROJECT_ID/$SERVICE_NAME \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --set-env-vars "SUPABASE_URL=$SUPABASE_URL,SUPABASE_KEY=$SUPABASE_KEY"
```

## Performance Tuning

- Set memory to 512MB minimum (1GB recommended for CPET analysis)
- Use CPU throttling disabled in production
- Enable request tracing with Google Cloud Logging
- Set up auto-scaling: min 1, max 100 instances
