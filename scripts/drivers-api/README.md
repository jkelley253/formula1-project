# Serve stored drivers through the existing API Lambda

The architecture is now:

```text
EC2 timer or manual start → Jolpica → formula1.public.drivers
Website → existing API Gateway → GetDriversFunction → formula1.public.drivers
```

The EC2 sync remains the only active upstream fetcher. The API reads the same
16 public fields from PostgreSQL, ordered by standings position then driver ID.
The existing frontend URL and JSON contract stay the same; no UI deployment is
needed for this backend change. The original Jolpica application module remains
in the repository, but the API handler no longer calls it.

## Deployment verified September 5, 2026 (Pacific)

The existing `formula1-drivers-service` stack was updated successfully without
replacing its API or Lambda. Two live requests returned HTTP 200 with all 16
fields matching PostgreSQL for **23 drivers**. A database snapshot before and
after confirmed that API reads did not change rows or `updated_at`. Browser
CORS was verified with `Origin: http://formula1project.com`.

Production permission checks confirmed that `drivers_api` can SELECT but cannot
INSERT/UPDATE/DELETE/TRUNCATE, and `driver_sync_ec2` retains write access. The
Monday timer remains enabled. All **49 backend tests** passed, including the
real PostgreSQL reader and existing writer tests. No frontend deployment is
required. The steps below support future verification and redeployment.

## Network and credentials

The reader Lambda attaches to the EC2 VPC using the database instance's subnet.
The stack creates a Lambda security group with outbound access only to the
existing EC2 security group on PostgreSQL's port. A separate ingress resource
adds the matching rule to EC2; its existing SSH rules remain intact. The API
uses EC2's private address, not its public IP.

The Lambda performs no upstream requests and makes no runtime calls to Secrets
Manager. This setup creates no NAT gateway or private endpoint and adds no
monthly credential-service charge. Existing Lambda, EC2, logging, storage, and
applicable traffic charges continue to apply. API Gateway still invokes the
Lambda normally through the AWS service.

A separate `drivers_api` login has SELECT-only access to `public.drivers`.
The writer keeps its existing `driver_sync_ec2` login. Reader connections also
default to read-only transactions, use a 3-second connection timeout, and bound
queries to 5 seconds. Each request closes its connection after reading. The
account's current concurrency quota is 10; the template does not reserve
concurrency because this low quota does not allow the usual unreserved buffer.
Reassess PostgreSQL connection limits if the account's concurrency grows.

The reader password is generated on EC2 and saved in
`/etc/formula1-driver-sync/reader.json` (root only). The deployment helper reads
it over verified SSH, passes it to CloudFormation through the AWS SDK in memory, and
never prints it or stores it locally. `DriversDatabasePassword` is a `NoEcho`
parameter. Lambda encrypts environment variables at rest using its default key.
Authorized administrators can still access Lambda configuration; do not print
or paste unfiltered environment configuration. Do not put the password in Git,
`samconfig.toml`, shell arguments, screenshots, or deployment logs.

## Prepare the reader role on EC2 (first deployment)

The EC2 sync installer must already have created `formula1.public.drivers` and
its bootstrap credential file. From the Mac project root, upload only these
new setup files:

```bash
scp -i ./formula1-db-key.pem scripts/ec2-sync/setup_reader.py \
  ec2-user@ec2-34-220-66-15.us-west-2.compute.amazonaws.com:~/formula1-driver-sync/scripts/ec2-sync/
scp -i ./formula1-db-key.pem scripts/install-ec2-driver-reader.sh \
  ec2-user@ec2-34-220-66-15.us-west-2.compute.amazonaws.com:~/formula1-driver-sync/scripts/
ssh -i ./formula1-db-key.pem \
  ec2-user@ec2-34-220-66-15.us-west-2.compute.amazonaws.com \
  'sudo bash ~/formula1-driver-sync/scripts/install-ec2-driver-reader.sh'
```

The installer uses the existing Docker image with the setup script mounted
read-only. It does not rebuild or restart the writer, change its password, or
modify the timer. Reruns reuse the reader credential file and verify the role
has no elevated or table-write privileges. If the role exists but the credential
file is missing, restore matching credentials rather than silently taking over
or rotating the role.

## Deploy from the Mac

Log into AWS if your CLI session has expired:

```bash
aws login
```

From the project root, prepare a change set (run `uv sync --all-packages --dev`
from `backend/` first if its virtual environment is missing):

```bash
backend/.venv/bin/python scripts/deploy-drivers-api.py \
  --instance-id i-0198d9059ad18ee5f \
  --ssh-host ec2-34-220-66-15.us-west-2.compute.amazonaws.com \
  --key ./formula1-db-key.pem
```

The helper discovers the instance's VPC, private IP, subnet, and security group,
checks the public hostname matches that instance, builds both existing Lambda
artifacts, uploads to the existing SAM bucket, and creates an UPDATE change set.
It requires the existing `formula1-drivers-service` and
`aws-sam-cli-managed-default` stacks. It preserves existing parameters including
CORS, and explicitly keeps `EnableDriverSync=false` because EC2 owns scheduling.
The helper expects the current one-security-group EC2 setup; if that changes,
review which group should receive database access.

Review the printed change-set ARN in CloudFormation and execute that change
set. Alternatively, add `--execute` to the helper command to create and execute
a new change set in one run. It stops rather than automatically applying a
resource removal or possible replacement. It never places a database password
in command arguments or local template files. SAM packaging receives short-lived
AWS session credentials only through the child process environment.

The first deployment needs all new database parameters. For subsequent API
changes, prefer the helper again so current reader credentials and network
settings are supplied consistently. Do not run the old API-only `sam deploy`
command for the first database-reader deployment.

## Verify the API and UI

From your Mac:

```bash
curl --fail --silent --show-error \
  https://8bp62sfmta.execute-api.us-west-2.amazonaws.com/api/drivers
```

Expect HTTP 200 and `{"drivers":[...]}`. Points remain JSON numbers, birthdays
are ISO date strings, team fields are arrays, and `updated_at` is not added to
the existing public contract. Empty tables return `{"drivers":[]}`.

On EC2, compare with the stored rows:

```bash
sudo docker exec formula1-postgres psql -U postgres -d formula1 -P pager=off \
  -c 'SELECT drivers_id, drivers_current_position, drivers_current_total_points FROM public.drivers ORDER BY drivers_current_position, drivers_id;'
```

Open the website's drivers page. The frontend already calls this API URL.
Successful responses retain the existing five-minute browser cache, so allow
that time or disable browser caching when checking an immediate manual update.
The reader does not fetch Jolpica to fill an empty table or hide a database
outage. Database/configuration failures produce HTTP 502 with the existing
friendly error message and `Cache-Control: no-store`. Logs contain only the
error class, without connection strings or credential-bearing exceptions.

To update data, connect to EC2 and run:

```bash
sudo systemctl start formula1-driver-sync.service
sudo journalctl -u formula1-driver-sync.service -n 10 --no-pager
```

Then query the API again. Reading through the API does not change `updated_at`.
Driver rows absent from later syncs remain stored under the current writer
policy; no season/roster filtering is introduced by this reader.

## Automated tests

Keep the Mac SSH tunnel open and the existing test `.pgpass` entry current.
From `backend/`:

```bash
DRIVER_SYNC_TEST_DSN='host=127.0.0.1 port=55432 dbname=formula1_test user=driver_sync_test connect_timeout=5' \
  uv run pytest -v
```

The suite includes PostgreSQL reader ordering, numeric/date/array serialization,
empty/error responses, and checks that API requests do not call upstream code.
It retains the writer upsert and rollback tests. Use the disposable test database;
the integration fixture creates and drops its own `public.drivers` table.

## Password changes and rollback

If the API password is rotated, update the EC2 reader credential file to match
and redeploy with the helper. Lambda does not retrieve that file at runtime.
The running writer uses a different role and does not need its credentials changed.

CloudFormation rolls back a failed stack update. A runtime failure after a
successful update needs investigation: verify EC2/PostgreSQL readiness, the
Lambda VPC subnet, both security-group rules, and the reader credentials. Do
not expose PostgreSQL publicly as a workaround. Keep the prior Lambda package
and stack template available if reverting the API deployment is necessary;
this deployment does not delete application rows or stop the EC2 timer.

References: [Lambda environment encryption](https://docs.aws.amazon.com/lambda/latest/dg/configuration-envvars-encryption.html),
[Lambda VPC configuration](https://docs.aws.amazon.com/lambda/latest/dg/configuration-vpc.html),
and [EC2 sync operations](../ec2-sync/README.md).
