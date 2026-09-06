# PostgreSQL on EC2

Paste the full contents of `ec2-postgres-user-data.sh` into **EC2 → Launch
instance → Advanced details → User data** when launching an Amazon Linux 2023
x86_64 instance. The reference AMI is
`al2023-ami-2023.12.20260831.0-kernel-6.18-x86_64`; select its regional AMI ID
in the console. This script targets AL2023's package manager and has not been
boot-tested on that exact AMI.

The script installs and enables Docker, pulls `postgres:18`, initializes the
`formula1` database, and publishes container TCP port 5432 on host
`0.0.0.0:5432`. PostgreSQL 18 data is mounted at `/var/lib/postgresql` in the
named volume `formula1-postgres-data`. Docker starts on boot, and the container
restarts unless explicitly stopped. EC2 user data normally runs only on first
boot. Manual reruns start an existing container without replacing it or
applying changed settings.

The instance needs outbound access to Amazon Linux repositories and Docker Hub
(for example, via a NAT gateway in a private subnet, or an internet gateway
and public IPv4 address in a public subnet).

## Connect Lambda

1. Attach Lambda to subnets in the EC2 instance's VPC and assign a Lambda
   security group. Its execution role needs VPC network-interface permissions
   (provided by `AWSLambdaVPCAccessExecutionRole`).
2. On the EC2 security group, allow **inbound TCP 5432**, with the **Lambda
   security group** as the source. Do not use `0.0.0.0/0` as the source.
3. Allow outbound TCP 5432 from the Lambda security group to the EC2 security
   group if outbound rules are restricted. Routes and network ACLs must allow
   the connection and return traffic.
4. Use the EC2 **private IPv4 address or private DNS name** as the database
   host. `0.0.0.0` is a listening address, not a connection destination.

Retrieve the generated bootstrap password over SSH or SSM:

```bash
sudo cat /etc/formula1-postgres/password
```

Initial connection settings:

```text
PGHOST=<EC2-private-IP-or-private-DNS>
PGPORT=5432
PGDATABASE=formula1
PGUSER=postgres
PGPASSWORD=<generated-password>
```

`postgres` is the bootstrap superuser. Create a separate application role with
the permissions your Lambda needs before using it for application traffic.
Store application credentials in AWS Secrets Manager and grant the Lambda
execution role access to that secret. This script does not configure TLS;
connections use password authentication over the private VPC network.

If your Lambda also calls public APIs (such as Jolpica), its VPC subnets need
outbound internet access through NAT; attaching Lambda to a public subnet
does not give the function a public IP.

## Verify and operate

```bash
sudo tail -n 100 /var/log/cloud-init-output.log
sudo docker ps --filter name=formula1-postgres
sudo docker logs --tail 100 formula1-postgres
sudo docker exec formula1-postgres pg_isready -h 127.0.0.1 -U postgres -d formula1
```

Readiness checks confirm the server is accepting connections; test a query
from Lambda to verify its network path and credentials.

The named volume survives container recreation and instance reboots. It lives
on the EC2 host's disk: deleting that EBS volume deletes the database. Arrange
backups and EBS retention for data you need to keep. Changing the password file
does not rotate an initialized database password, and changing the image's
major version requires a PostgreSQL migration.

References: [AWS Docker installation guidance](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/create-container-image.html),
[official PostgreSQL image](https://hub.docker.com/_/postgres), and
[Lambda VPC configuration](https://docs.aws.amazon.com/lambda/latest/dg/configuration-vpc.html).

## Scheduled driver updates on EC2

The selected deployment runs the driver sync on this existing EC2 server.
See [EC2 driver sync setup](ec2-sync/README.md) for upload, installation, manual
updates, the Monday 00:01 Pacific timer, logs, and pause/update instructions.
The installer is `scripts/install-ec2-driver-sync.sh`; the original PostgreSQL
bootstrap above remains unchanged.
