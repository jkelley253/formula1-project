# Backend microservice refactor

## Plan and architecture

The backend is a UV workspace of independently deployable AWS SAM
microservices. Each service owns its Lambda functions, API Gateway, domain,
external adapters, dependencies, tests, configuration, and CloudFormation
stack. Services may contain multiple closely related Lambda functions.

The first service preserves `GET /api/drivers`, its `{"drivers": [...]}`
response, its `502` error contract, CORS behavior, Python 3.12 ARM64 runtime,
memory and timeout settings, X-Ray tracing, and least-privilege permissions.
Every service receives its own API Gateway URL. The website remains
`formula1project.com`; only the frontend's `VITE_API_BASE_URL` changes. The S3
website currently uses HTTP, so its deployed CORS origin must include that
scheme.

Shared infrastructure-only Python helpers live in `packages/lambda-common`.
Formula 1 business models and Jolpica behavior remain owned by the drivers
service. Cross-service calls, databases, messaging, authentication, and
service discovery are not part of this refactor.

```text
backend/
├── pyproject.toml
├── uv.lock
├── Makefile
├── packages/
│   └── lambda-common/
│       ├── pyproject.toml
│       ├── src/formula1_lambda_common/
│       └── tests/
└── services/
    └── drivers/
        ├── pyproject.toml
        ├── template.yaml
        ├── samconfig.toml
        ├── build.mk
        ├── README.md
        ├── src/drivers_service/
        │   ├── handlers/
        │   ├── application/
        │   ├── domain/
        │   └── infrastructure/
        └── tests/
```

Handlers contain Lambda transport entrypoints, application modules coordinate
use cases, domain modules contain service-owned models and rules, and
infrastructure modules adapt external systems.

## UV workspace workflow

There is one root lockfile. Each service and shared package has its own
`pyproject.toml` and declares only its dependencies. Add dependencies to the
owning package from `backend/`:

```bash
uv add --package formula1-drivers-service package-name
uv add --package formula1-lambda-common package-name
```

Install every workspace member and run every test:

```bash
cd backend
uv sync --all-packages --dev
uv run pytest
```

Run only the drivers tests:

```bash
uv run --package formula1-drivers-service pytest services/drivers/tests
```

SAM invokes the workspace Makefile, which includes each service-owned
`build.mk`. The service recipe exports locked production dependencies with UV,
installs them for the Lambda platform, and copies the service and shared
package sources into the artifact. No `requirements.txt` is maintained in the
repository.

## Build and run the drivers service

```bash
cd backend/services/drivers
sam validate --lint
sam build
sam local start-api
```

In another terminal:

```bash
curl http://127.0.0.1:3000/api/drivers
```

Invoke the Lambda directly with an API Gateway event file when needed:

```bash
sam local invoke GetDriversFunction --event event.json
```

## Deploy and inspect the drivers service

For a first deployment in a new AWS account or region:

```bash
cd backend/services/drivers
sam build
sam deploy --guided
```

The checked-in configuration deploys the `formula1-drivers-service` stack in
`us-west-2`. Repeat deployments use:

```bash
sam build
sam deploy
```

Restrict production CORS to the existing website:

```bash
sam deploy --parameter-overrides CorsAllowOrigin=http://formula1project.com
```

Look up the service URL:

```bash
aws cloudformation describe-stacks \
  --stack-name formula1-drivers-service \
  --query 'Stacks[0].Outputs[?OutputKey==`DriversApiUrl`].OutputValue' \
  --output text
```

## Add a microservice

1. Create `backend/services/<service>/` with its own `pyproject.toml`,
   `template.yaml`, `samconfig.toml`, `build.mk`, `README.md`, `src`, and tests.
2. Use a uniquely named import package under `src/` and the standard handlers,
   application, domain, and infrastructure layers.
3. Give the SAM stack and API output service-specific names.
4. Reference `formula1-lambda-common` as a workspace dependency only if the
   service exposes HTTP Lambda handlers.
5. Add each function's SAM build target to the service's `build.mk` and include
   that file from the workspace Makefile.
6. Run `uv lock`, workspace tests, `sam validate --lint`, and `sam build`.
7. Document routes, contracts, integrations, variables, and exact commands in
   the service README.

## Add a Lambda to an existing service

1. Add its handler under the service's `handlers` package and keep business
   behavior in the application/domain layers.
2. Add the function, integration, route, and narrowly scoped invocation
   permission to the service's SAM template.
3. Add a matching `build-<FunctionLogicalId>` target to the service's
   `build.mk`. It may reuse the same UV export and source-copy recipe.
4. Add handler contract and application tests, then validate and build the
   complete service before deployment.

## Staged migration and rollback

1. Deploy `formula1-drivers-service` beside the existing
   `formula1-backend` stack.
2. Retrieve `DriversApiUrl` and compare the old and new endpoint status,
   headers, and JSON structure.
3. Build the frontend with the new API Gateway base URL (exclude
   `/api/drivers` from the value):

   ```bash
   cd frontend
   VITE_API_BASE_URL=https://NEW_API_ID.execute-api.us-west-2.amazonaws.com npm run build
   ```

4. Deploy the compiled frontend to the existing website and verify its network
   requests use the new service. The website URL does not change.
5. Keep the previous API base URL available as the rollback value. If the new
   service fails, rebuild/redeploy the frontend with that old value.
6. Delete the old `formula1-backend` CloudFormation stack only after the new
   service and production UI have been verified.
