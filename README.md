# Formula 1 Project

React frontend with independently deployable AWS Lambda microservices for
Formula 1 data.

- [`frontend/`](frontend/): Vite/React web application
- [`backend/`](backend/): UV workspace containing AWS SAM microservices

Service documentation:

- [Driver standings](backend/services/drivers/README.md)
- [Driver season and career statistics](backend/services/driver_stats/README.md)
- [Driver stats installation and operations](scripts/driver-stats/README.md)
- [Driver stats feature plan](driver_stats_feature.md), separate from the service README

## Architecture

```text
Browser -> S3 frontend -> Drivers API Gateway -> Drivers Lambda -> PostgreSQL on EC2
                      -> Stats API Gateway   -> Stats Lambda   -> PostgreSQL on EC2
EC2 scheduled jobs -> Jolpica API -> PostgreSQL standings and stats tables
```

Production API:

```text
https://8bp62sfmta.execute-api.us-west-2.amazonaws.com/api/drivers
```

API Gateway HTTP API routes must not include a trailing slash. Use
`/api/drivers`, not `/api/drivers/`.

## Prerequisites

- Node.js and npm
- Python 3.12+, uv, AWS CLI, and AWS SAM CLI
- Docker Desktop for local Lambda execution
- A non-root IAM or SSO identity with permission to manage CloudFormation,
  Lambda, API Gateway, IAM roles, S3, and SAM deployment assets

Verify your setup:

```bash
aws --version
sam --version
docker --version
aws sts get-caller-identity
```

## Deploy the backend

```bash
cd backend
uv sync --all-packages --dev
uv run pytest
cd services/drivers
sam validate --lint
sam build
sam deploy
```

The service-local `samconfig.toml` deploys the `formula1-drivers-service` stack
to `us-west-2`. For the first deployment in another account or region, use
`sam deploy --guided`.

Retrieve and test the deployed URL:

```bash
aws cloudformation describe-stacks \
  --stack-name formula1-drivers-service \
  --query 'Stacks[0].Outputs[?OutputKey==`DriversApiUrl`].OutputValue' \
  --output text
curl https://8bp62sfmta.execute-api.us-west-2.amazonaws.com/api/drivers
```

## Deploy the frontend

```bash
cd frontend
npm install
npm run lint
npm run build
aws s3 sync dist/ s3://formula1project.com --delete
```

`--delete` removes old hashed assets that no longer exist in `dist/`. Omit it
if those files must be retained.

Driver names open shareable profiles at `/#/drivers/{driver_id}`. The stats API
is selected by `VITE_DRIVER_STATS_API_BASE_URL`; see the frontend README for
its production setting. Run `npm test` to verify profile navigation and states.

To build against another backend:

```bash
VITE_API_BASE_URL=https://example.execute-api.us-west-2.amazonaws.com npm run build
```

Vite embeds the endpoint at build time, so rebuild and sync after changing it.

## Run locally

Start the backend:

```bash
cd backend/services/drivers
sam build
sam local start-api
```

In another terminal, start the frontend:

```bash
cd frontend
VITE_API_BASE_URL=http://127.0.0.1:3000 npm run dev
```

Open `http://localhost:5173`. See [`backend/README.md`](backend/README.md) and
[`frontend/README.md`](frontend/README.md) for component-specific details.
