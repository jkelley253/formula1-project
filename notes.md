# AWS setup and deployment notes

This document explains how the Formula 1 frontend and backend were prepared
for AWS, how they were deployed, and which AWS settings were not created from
this repository.

## Final architecture

```text
User's browser
    |
    v
S3 bucket: formula1project.com
    |  serves the compiled React application
    v
API Gateway HTTP API
    |  GET /api/drivers
    v
AWS Lambda (Python 3.12)
    |
    v
Jolpica Formula 1 API
```

The deployed backend URL is:

```text
https://xg3iib3hq8.execute-api.us-west-2.amazonaws.com/api/drivers
```

The AWS region is `us-west-2`, and the CloudFormation stack is named
`formula1-backend`.

## AWS authentication and tools

The deployments use the AWS CLI credentials configured on the computer. The
current identity and region can be checked with:

```bash
aws sts get-caller-identity
aws configure get region
```

An IAM user or AWS IAM Identity Center/SSO identity should be used for normal
work. Using the AWS account root user for CLI deployments is not recommended.

The required local tools are:

- AWS CLI for inspecting AWS and uploading the frontend to S3
- AWS SAM CLI for building and deploying the serverless backend
- Docker Desktop for running Lambda locally with `sam local`
- Python 3.12 and uv for backend tests
- Node.js and npm for the React frontend

## Backend setup

The original Django server was replaced with a serverless Python application.
The Lambda source is under `backend/src/`, and the infrastructure definition is
`backend/template.yaml`.

### What AWS SAM does

AWS SAM (Serverless Application Model) is a simplified way to describe
serverless AWS infrastructure. The `Transform` line in `template.yaml` tells
CloudFormation to convert SAM resources into regular AWS resources during
deployment.

This project defines:

- `DriversApi`: an API Gateway HTTP API with a `$default` stage
- `GetDriversFunction`: the Python 3.12 Lambda function
- `DriversIntegration`: connects API Gateway to Lambda using an AWS proxy
  integration
- `DriversRoute`: registers `GET /api/drivers`
- `GetDriversInvokePermission`: permits only this API Gateway API to invoke the
  Lambda function
- `DriversApiUrl`: a CloudFormation output containing the public endpoint

The integration and route are explicit CloudFormation resources. They were
made explicit after the original generated API definition deployed an API but
did not produce a usable route.

API Gateway HTTP API rejected the original route ending in `/`. Therefore the
valid path is `/api/drivers`, without a trailing slash.

### SAM configuration

`backend/samconfig.toml` stores repeatable deployment settings:

- stack name: `formula1-backend`
- region: `us-west-2`
- automatic SAM deployment-bucket resolution
- permission to create the IAM role required by Lambda
- CORS parameter currently set to `*`

For production, CORS should ideally be restricted to the real frontend origin
instead of allowing every origin.

### Building and testing the backend

```bash
cd backend
uv sync --dev
uv run pytest
sam validate --lint
sam build
```

`uv sync --dev` installs development dependencies such as pytest.
`sam validate --lint` checks the infrastructure template. `sam build` copies
the Lambda source into `.aws-sam/build/` and produces the transformed template
that SAM will deploy.

The Lambda runtime itself has no third-party Python packages. It uses Python's
standard library to call Jolpica, which keeps the deployment package small.

### Deploying the backend

The first deployment can be configured interactively:

```bash
cd backend
sam build
sam deploy --guided
```

After `samconfig.toml` exists, later deployments use:

```bash
sam build
sam deploy
```

During deployment, SAM uploads build artifacts to its managed S3 deployment
bucket and creates or updates the `formula1-backend` CloudFormation stack.
CloudFormation then creates and manages API Gateway, Lambda, the Lambda IAM
execution role, invocation permission, and X-Ray tracing configuration.

Verify the result with:

```bash
aws cloudformation describe-stacks \
  --stack-name formula1-backend \
  --query 'Stacks[0].Outputs[?OutputKey==`DriversApiUrl`].OutputValue' \
  --output text

aws apigatewayv2 get-routes \
  --api-id xg3iib3hq8 \
  --query 'Items[].RouteKey' \
  --output text

curl https://xg3iib3hq8.execute-api.us-west-2.amazonaws.com/api/drivers
```

The verified route is `GET /api/drivers`, and the endpoint returned HTTP 200
with 23 driver records when it was deployed.

## Frontend setup

The frontend is a Vite/React application under `frontend/`. It requests driver
data from API Gateway and renders the response as a standings table.

The production API base URL is the default in:

```text
frontend/src/features/drivers/api/driversApi.js
```

It can be replaced at build time without editing source code:

```bash
VITE_API_BASE_URL=https://another-api.example.com npm run build
```

Vite environment variables are embedded into the compiled JavaScript during
the build. Changing `VITE_API_BASE_URL` after building does not change files
already inside `dist/`; the frontend must be rebuilt and uploaded again.

### What `dist/` is

Running `npm run build` creates `frontend/dist/`. This is the production-ready
static website, not source code. It contains files such as:

- `index.html`
- compiled and minified JavaScript under `assets/`
- compiled CSS under `assets/`
- copied public assets such as icons and the favicon

Only the contents of `dist/` are uploaded to the website bucket. The React
source, `node_modules`, and development server are not deployed to S3.

### Building and deploying the frontend

```bash
cd frontend
npm install
npm run lint
npm run build
aws s3 sync dist/ s3://formula1project.com --delete
```

`npm install` installs frontend dependencies. `npm run lint` checks the source,
and `npm run build` produces `dist/`.

`aws s3 sync` compares local files with objects in the bucket and uploads new
or changed files. The `--delete` option removes old hashed assets from S3 when
they no longer exist in the current `dist/`. It can be omitted when old files
must be preserved.

The frontend was deployed from this workspace with:

```bash
aws s3 sync dist/ s3://formula1project.com
```

That upload did not use `--delete`, so older hashed build assets remained in
the bucket. Future deployments can use `--delete` after confirming that the
bucket contains only this website's generated files.

## Local development

Start the backend from one terminal:

```bash
cd backend
sam build
sam local start-api
```

Start the frontend from another terminal and override the production API URL:

```bash
cd frontend
VITE_API_BASE_URL=http://127.0.0.1:3000 npm run dev
```

Then open `http://localhost:5173`. The local backend route is
`http://127.0.0.1:3000/api/drivers`.

`sam local` uses a Lambda emulation container, so Docker Desktop must be
running. Docker also needs permission to pull the public AWS SAM runtime image.

## AWS Console work not performed here

No AWS Console pages were changed during this work. Backend infrastructure was
created and updated through SAM and CloudFormation, and the frontend files were
uploaded with the AWS CLI.

The S3 bucket `formula1project.com` already existed before the frontend sync.
This repository did not create or verify the following website-hosting pieces:

- creation of the `formula1project.com` S3 bucket
- S3 static website hosting settings and index/error documents
- the S3 bucket policy or public-access settings
- a CloudFront distribution or Origin Access Control
- an ACM TLS certificate for HTTPS
- Route 53 hosted-zone and DNS records for `formula1project.com`
- CloudFront cache invalidations after a frontend deployment

Those items may have been configured manually in the AWS Console, configured
elsewhere, or may still need to be completed. They should be checked in the S3,
CloudFront, ACM, and Route 53 consoles before assuming the custom domain is
fully deployed.

The SAM-managed resources should not normally be edited manually in the AWS
Console. Console edits can cause CloudFormation drift and may be overwritten by
the next `sam deploy`.

## Recommended production follow-ups

1. Use a non-root IAM or SSO identity for deployments.
2. Restrict API Gateway CORS to the actual frontend HTTPS origin.
3. Put CloudFront in front of the S3 bucket and keep the bucket private.
4. Attach an ACM certificate and Route 53 records for the custom domain.
5. Add cache-control metadata for hashed assets and conservative caching for
   `index.html`.
6. Automate `sam deploy`, the frontend build, S3 sync, and CloudFront
   invalidation in CI/CD.
