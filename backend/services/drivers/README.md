# Drivers microservice

The drivers service owns current Formula 1 driver standings. Its API Lambda
retrieves standings from Jolpica, maps them into the service's domain model,
and returns the contract consumed by the frontend.

## API

`GET /api/drivers` returns:

```json
{"drivers": []}
```

If Jolpica cannot provide usable standings, the service returns HTTP `502`:

```json
{"error": "Driver standings are temporarily unavailable"}
```

## Configuration and integrations

| Variable | Default | Purpose |
| --- | --- | --- |
| `CORS_ALLOW_ORIGIN` | `*` | Browser origin allowed by the response |
| `STANDINGS_API_BASE_URL` | `https://api.jolpi.ca/ergast/f1` | Jolpica-compatible API base URL |

The service calls the public Jolpica API and requires no application-specific
IAM permissions.

## Commands

Run these from `backend/` unless a command changes directory explicitly.

```bash
uv sync --all-packages --dev
uv run --package formula1-drivers-service pytest services/drivers/tests
cd services/drivers
sam validate --lint
sam build
sam local start-api
```

With the local API running, call:

```bash
curl http://127.0.0.1:3000/api/drivers
```

Deploy the service for the first time with `sam deploy --guided`, or use the
checked-in configuration with:

```bash
cd backend/services/drivers
sam build
sam deploy
```

Look up the deployed endpoint:

```bash
aws cloudformation describe-stacks \
  --stack-name formula1-drivers-service \
  --query 'Stacks[0].Outputs[?OutputKey==`DriversApiUrl`].OutputValue' \
  --output text
```

For production, deploy with the website origin:

```bash
sam deploy --parameter-overrides CorsAllowOrigin=http://formula1project.com
```

The site currently uses the S3 website endpoint through HTTP. Change this
origin to `https://formula1project.com` after HTTPS is configured for the
website, such as through CloudFront.
