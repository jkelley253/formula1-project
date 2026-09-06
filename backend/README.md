# Formula 1 serverless backend

This directory is a UV workspace containing independently deployable AWS SAM
microservices and shared infrastructure packages.

- [`services/drivers/`](services/drivers/): current driver standings API
- [`services/driver_stats/`](services/driver_stats/): stored season and career statistics, with an EC2 sync job
- [`packages/lambda-common/`](packages/lambda-common/): shared Lambda HTTP helpers

See [`../microservice_refactor.md`](../microservice_refactor.md) for the full
architecture and workflow, and
[`services/drivers/README.md`](services/drivers/README.md) for service-specific
commands and contracts.

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
uv sync --all-packages --dev
uv run pytest
```

## Run locally

```bash
cd services/drivers
sam build
sam local start-api
curl http://127.0.0.1:3000/api/drivers
```

## Deploy

The first deployment prompts for the AWS region and saves it to
`samconfig.toml`:

```bash
cd services/drivers
sam build
sam deploy --guided
```

For later deployments, run `sam deploy` from the service directory. Its
`DriversApiUrl` stack output contains the frontend API endpoint.

For production, restrict CORS to the frontend origin:

```bash
sam deploy --parameter-overrides CorsAllowOrigin=http://formula1project.com
```

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `CORS_ALLOW_ORIGIN` | `*` | Browser origin allowed by the response |
| `STANDINGS_API_BASE_URL` | `https://api.jolpi.ca/ergast/f1` | Override for testing or an alternate compatible feed |

The template enables active X-Ray tracing and grants no application-specific
IAM permissions because the function only makes a public HTTPS request.
