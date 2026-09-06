# Drivers microservice

The drivers service owns Formula 1 driver standings. Its API Lambda reads
stored standings from PostgreSQL on EC2 and returns the existing frontend
contract. The separate EC2 sync job fetches and maps Jolpica data on Mondays
or when manually triggered. See the [database-reader deployment guide](../../../scripts/drivers-api/README.md).

## API

`GET /api/drivers` returns:

```json
{"drivers": []}
```

If PostgreSQL cannot provide standings, the service returns HTTP `502` with
`Cache-Control: no-store`:

```json
{"error": "Driver standings are temporarily unavailable"}
```

## Configuration and integrations

| Variable | Default | Purpose |
| --- | --- | --- |
| `CORS_ALLOW_ORIGIN` | `*` | Browser origin allowed by the response |
| `DRIVERS_DB_HOST` | Required | EC2 private database address |
| `DRIVERS_DB_PORT` | `5432` | PostgreSQL port |
| `DRIVERS_DB_NAME` | `formula1` | Application database |
| `DRIVERS_DB_USER` | Required | Dedicated read-only role |
| `DRIVERS_DB_PASSWORD` | Required | Encrypted Lambda environment variable |
| `STANDINGS_API_BASE_URL` | `https://api.jolpi.ca/ergast/f1` | Upstream URL for sync jobs only |

The API needs VPC network-interface permissions and private access to EC2
PostgreSQL. It makes no runtime Jolpica or Secrets Manager calls. Existing
upstream modules and the optional scheduled Lambda remain available for the
original integration, while the EC2 job is the selected writer.

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

For the database-reader migration, use the deployment helper in the
[reader guide](../../../scripts/drivers-api/README.md), which securely supplies
the new network and credential parameters. The following legacy SAM commands
require those parameters to have been supplied or preserved from a prior deployment:

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

## EC2 deployment (selected)

Run the weekly sync on the existing PostgreSQL EC2 server using the
[EC2 installer and operations guide](../../../scripts/ec2-sync/README.md).
This supports manual starts and Monday 00:01 Pacific scheduling with a local
application credential file and no NAT gateway or Secrets Manager requirement.
Keep the SAM driver-sync feature disabled when using the EC2 timer.

## Weekly PostgreSQL sync

`SyncDriversFunction` independently fetches and maps the same 16 driver fields
from Jolpica, then upserts them into `public.drivers` on your existing EC2
PostgreSQL server. The API reads those stored standings without an upstream call.
The schedule is Monday at **12:01 AM America/Los_Angeles**, including daylight
saving changes. EventBridge schedules have minute-level precision.

The feature defaults to disabled. `EnableDriverSync=true` creates the Lambda
and enables its schedule; setting it back to `false` removes those resources
without changing database rows or the existing API. No EC2 or network resources
are provisioned by this service.

### Prepare the database

Follow the existing [EC2 PostgreSQL setup](../../../scripts/README.md).
From a machine with private database
access, connect as the database administrator and run:

```bash
psql -h <EC2-private-host> -U postgres -d formula1 -W \
  -v ON_ERROR_STOP=1 -f sql/001_create_drivers.sql
```

Run these once in that administrator's `psql` session to create the application
role and set its password interactively:

```sql
CREATE ROLE driver_sync LOGIN;
\password driver_sync
GRANT CONNECT ON DATABASE formula1 TO driver_sync;
GRANT USAGE ON SCHEMA public TO driver_sync;
GRANT SELECT, INSERT, UPDATE ON TABLE public.drivers TO driver_sync;
```

The setup SQL creates a new table if absent; it does not migrate an existing
incompatible table. Lambda has no table-creation or deletion responsibilities.
All 16 domain field names are preserved as columns. Team fields use `TEXT[]`,
birthday uses `DATE`, points use `NUMERIC`, and `updated_at` records the database
transaction time in a timezone-aware timestamp.

Create a Secrets Manager secret in the deployment region using this JSON shape
and your real application credentials (do not commit them):

```json
{
  "host": "<EC2-private-host>",
  "port": 5432,
  "dbname": "formula1",
  "username": "driver_sync",
  "password": "<application-role-password>",
  "sslmode": "prefer"
}
```

`port` defaults to `5432`; `sslmode` defaults to `prefer`, which permits the
private-network, non-TLS PostgreSQL bootstrap configuration. For TLS-configured
servers, configure the corresponding SSL mode and any required trust material.
Use the default Secrets Manager encryption key; if using a customer-managed KMS
key, additionally grant the new Lambda role `kms:Decrypt` for that key and allow
it in the key policy. Credentials are read on each nonempty sync, allowing rotation.

### Network and deployment

Supply private subnet IDs in the EC2 VPC with NAT egress to Jolpica. Secrets
Manager also needs an accessible HTTPS endpoint, through NAT or a VPC endpoint.
Allow EC2 security-group ingress on TCP 5432 from the Lambda security group and
matching outbound access from Lambda. A Lambda attached to a public subnet does
not obtain a public IP.

From this directory:

```bash
sam validate --lint
sam build
sam deploy --parameter-overrides \
  CorsAllowOrigin=http://formula1project.com \
  EnableDriverSync=true \
  DriverSyncSubnetIds=subnet-<first>,subnet-<second> \
  DriverSyncSecurityGroupIds=sg-<lambda> \
  DatabaseSecretArn=arn:aws:secretsmanager:us-west-2:<account>:secret:<name>
```

Replace all placeholders before running. Enabling sync requires nonempty
network and secret parameters. Save those overrides in your deployment process
for subsequent deployments; the checked-in configuration remains API-only.
The function inherits Python 3.12/ARM64 and has a 60-second timeout, reserved
concurrency of one, and two asynchronous retries within a one-hour event age.
Scheduler delivery also has two retries within one hour.

### Verify and monitor

Read `SyncDriversFunctionName` from the stack outputs, then invoke it twice:

```bash
aws cloudformation describe-stacks --stack-name formula1-drivers-service \
  --query 'Stacks[0].Outputs[?OutputKey==`SyncDriversFunctionName`].OutputValue' \
  --output text
aws lambda invoke --function-name <function-name> --payload '{}' /tmp/driver-sync-first.json
aws lambda invoke --function-name <function-name> --payload '{}' /tmp/driver-sync-second.json
```

Check both invocation metadata for absence of `FunctionError` and response files
for `outcome: success` and a positive `driver_count`. Query `public.drivers` to
confirm stable row counts, field values, and refreshed `updated_at`; call the
existing `/api/drivers` endpoint to verify its contract. Confirm the schedule
expression and timezone in EventBridge Scheduler.

Each batch commits atomically. Retries update existing driver IDs without
creating duplicates. Drivers absent from later results remain stored; this is
a latest-per-driver table, not a historical snapshot or exclusively current
season roster. Empty upstream results log `skipped` and leave the database
unchanged. Malformed responses and database errors fail the invocation; database
errors roll back the entire batch.

CloudWatch logs include `outcome`, `driver_count`, and `duration_ms`, plus an
error class on failure. Exception messages, payloads, and database credentials
are not logged. Monitor Lambda Errors/Throttles and Scheduler delivery errors;
there is no additional alarm or dead-letter queue in this feature.

### Tests

From `backend/`, run the backend suite normally. PostgreSQL tests skip unless
`DRIVER_SYNC_TEST_DSN` points to a **disposable** database with no `public.drivers`
table. They create and remove only their test table and refuse to overwrite an
existing table.

```bash
uv run pytest services/drivers/tests packages/lambda-common/tests
DRIVER_SYNC_TEST_DSN='postgresql://<user>:<password>@127.0.0.1:<port>/<test-db>' \
  uv run pytest services/drivers/tests/test_sync_postgres.py
```

Implementation references: [SAM ScheduleV2](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-property-function-schedulev2.html)
and [Psycopg transactions](https://www.psycopg.org/psycopg3/docs/basic/transactions.html).
