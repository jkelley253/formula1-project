# Formula 1 serverless backend

This directory is an AWS SAM application. API Gateway invokes a Python 3.12
Lambda function for `GET /api/drivers`; the function reads the current driver
standings from Jolpica and returns the same `{"drivers": [...]}` contract used by
the former Django endpoint.

The deployed runtime has no third-party Python dependencies. That keeps cold
starts and the Lambda bundle small and avoids packaging FastF1, Pandas, and
their native dependencies for a standings-only request.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)
- Docker, for `sam local` commands
- AWS credentials, for deployment

## Test

```bash
uv sync --dev
uv run pytest
```

## Run locally

```bash
sam build
sam local start-api
curl http://127.0.0.1:3000/api/drivers
```

## Deploy

The first deployment prompts for the AWS region and saves it to
`samconfig.toml`:

```bash
sam build
sam deploy --guided
```

For later deployments, run `sam deploy`. The stack output named
`DriversApiUrl` contains the frontend API URL.

For production, restrict CORS to the frontend origin:

```bash
sam deploy --parameter-overrides CorsAllowOrigin=https://formula1project.com
```

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `CORS_ALLOW_ORIGIN` | `*` | Browser origin allowed by the response |
| `STANDINGS_API_BASE_URL` | `https://api.jolpi.ca/ergast/f1` | Override for testing or an alternate compatible feed |

The template enables active X-Ray tracing and grants no application-specific
IAM permissions because the function only makes a public HTTPS request.
