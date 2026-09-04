# Deployment guide

This guide deploys the drivers microservice and the React frontend. The public
website is currently served from `http://formula1project.com`; the frontend
build is configured to call the drivers service's API Gateway URL.

## Prerequisites

- AWS CLI credentials are configured for the target AWS account.
- AWS SAM CLI, UV, Python 3.12, Node.js, and npm are installed.
- The deployment region is `us-west-2` unless intentionally overridden.

Confirm the active AWS identity before deploying:

```bash
aws sts get-caller-identity
```

## Deploy the backend

From the repository root, install and test the complete backend workspace:

```bash
cd backend
uv sync --all-packages --dev
uv run pytest
```

Validate, build, and deploy the drivers service:

```bash
cd services/drivers
sam validate --lint
sam build
sam deploy --parameter-overrides CorsAllowOrigin=http://formula1project.com
```

The checked-in SAM configuration deploys the service as the
`formula1-drivers-service` CloudFormation stack in `us-west-2`. For a first
deployment into a different AWS account or region, use `sam deploy --guided`
and save the resulting configuration.

Retrieve the complete drivers endpoint:

```bash
DRIVERS_API_URL=$(aws cloudformation describe-stacks \
  --stack-name formula1-drivers-service \
  --region us-west-2 \
  --query 'Stacks[0].Outputs[?OutputKey==`DriversApiUrl`].OutputValue' \
  --output text)

echo "$DRIVERS_API_URL"
curl --fail --show-error "$DRIVERS_API_URL"
```

The output ends in `/api/drivers`. The frontend environment variable requires
the base URL without that route suffix:

```bash
API_BASE_URL=${DRIVERS_API_URL%/api/drivers}
echo "$API_BASE_URL"
```

## Deploy the frontend

Return to the repository root, install dependencies, run checks, and build the
frontend with the deployed API base URL:

```bash
cd ../../../frontend
npm install
npm run lint
VITE_API_BASE_URL="$API_BASE_URL" npm run build
```

Upload the compiled frontend to the existing website bucket:

```bash
aws s3 sync dist/ s3://formula1project.com --delete
```

The `--delete` option removes obsolete hashed build assets from S3. It does not
delete source files in the repository.

## Verify production

Verify the backend endpoint and website after both deployments:

```bash
curl --fail --show-error "$DRIVERS_API_URL"
curl --fail --show-error http://formula1project.com
```

Open `http://formula1project.com` in a browser and confirm that driver data
loads successfully. In the browser's developer tools, verify that the request
to `/api/drivers` uses the new API Gateway hostname and returns HTTP `200`.

When HTTPS is added to the website, update `CorsAllowOrigin` to
`https://formula1project.com` and redeploy the backend before switching the
site to HTTPS.

Do not remove the previous `formula1-backend` stack until the new service and
frontend have been verified in production.
