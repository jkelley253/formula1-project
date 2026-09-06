"""Prepare or deploy the driver stats stack without putting passwords in CLI arguments.

Requires AWS CLI login, SAM, and SSH access to the already-prepared EC2 reader.
Defaults to creating a reviewable change set. Add --execute to apply it.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

import boto3


ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "backend/services/driver_stats"


def capture(command: list[str], *, env=None, cwd=None) -> str:
    result = subprocess.run(command, capture_output=True, text=True, env=env, cwd=cwd)
    if result.returncode:
        # Tool output might contain configuration values. Never print it blindly.
        raise RuntimeError(f"{Path(command[0]).name} {command[1]} failed (exit {result.returncode}); check authentication, permissions, and the documented prerequisites")
    return result.stdout


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--ssh-host", required=True, help="Verified public EC2 hostname")
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--region", default="us-west-2")
    parser.add_argument("--stack", default="formula1-driver-stats-service")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.ssh_host.startswith("-") or any(c.isspace() for c in args.ssh_host):
        raise ValueError("Invalid SSH hostname")

    def aws(*command):
        options = ["aws", *command, "--region", args.region, "--output", "json", "--no-cli-pager"]
        output = capture(options)
        return json.loads(output) if output.strip() else {}

    existing = aws("cloudformation", "list-stacks", "--stack-status-filter", "CREATE_COMPLETE", "UPDATE_COMPLETE", "UPDATE_ROLLBACK_COMPLETE")
    exists = any(item["StackName"] == args.stack for item in existing["StackSummaries"])
    stack = aws("cloudformation", "describe-stacks", "--stack-name", args.stack)["Stacks"][0] if exists else {}
    instances = aws("ec2", "describe-instances", "--instance-ids", args.instance_id)["Reservations"]
    instance = instances[0]["Instances"][0]
    if instance["State"]["Name"] != "running" or args.ssh_host not in (instance.get("PublicDnsName"), instance.get("PublicIpAddress")):
        raise ValueError("SSH host does not match the running EC2 instance")
    groups = instance["SecurityGroups"]
    if len(groups) != 1:
        raise ValueError("This helper expects one EC2 security group; select the intended group explicitly in a reviewed deployment")
    credentials = json.loads(capture([
        "ssh", "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=yes",
        "-i", str(args.key.resolve()), f"ec2-user@{args.ssh_host}",
        "sudo -n cat /etc/formula1-driver-stats/reader.json",
    ]))
    if credentials.get("username") != "driver_stats_api" or credentials.get("dbname") != "formula1" or not credentials.get("password"):
        raise ValueError("Unexpected reader credentials")

    # SAM's embedded SDK may not yet support aws login. Export the current CLI
    # session into this child process's environment only; never persist or print it.
    session = json.loads(capture(["aws", "configure", "export-credentials", "--format", "process"]))
    sam_env = {**os.environ, "AWS_ACCESS_KEY_ID": session["AccessKeyId"], "AWS_SECRET_ACCESS_KEY": session["SecretAccessKey"]}
    if session.get("SessionToken"):
        sam_env["AWS_SESSION_TOKEN"] = session["SessionToken"]
    else:
        sam_env.pop("AWS_SESSION_TOKEN", None)
    if not args.skip_build:
        print("Building Lambda artifacts...", flush=True)
        capture(["sam", "build", "--no-cached"], env=sam_env, cwd=SERVICE)
    bucket_stack = aws("cloudformation", "describe-stacks", "--stack-name", "aws-sam-cli-managed-default")["Stacks"][0]
    bucket = next(item["OutputValue"] for item in bucket_stack["Outputs"] if item["OutputKey"] == "SourceBucket")
    with tempfile.TemporaryDirectory(prefix="formula1-api-package-") as temporary:
        template_path = Path(temporary) / "packaged.yaml"
        print("Uploading code to the existing SAM artifact bucket...", flush=True)
        capture([
            "sam", "package", "--template-file", str(SERVICE / ".aws-sam/build/template.yaml"),
            "--s3-bucket", bucket, "--s3-prefix", "formula1-driver-stats-service",
            "--region", args.region, "--output-template-file", str(template_path),
        ], env=sam_env, cwd=SERVICE)
        template = template_path.read_text()

    values = {
        "StatsVpcId": instance["VpcId"],
        # Same AZ as this single EC2 database avoids unnecessary cross-AZ traffic.
        "StatsApiSubnetIds": instance["SubnetId"],
        "DatabaseSecurityGroupId": groups[0]["GroupId"],
        "StatsDatabaseHost": instance["PrivateIpAddress"],
        "StatsDatabasePort": "5432", "StatsDatabaseName": credentials["dbname"],
        "StatsDatabaseUser": credentials["username"], "StatsDatabasePassword": credentials["password"],
        "CorsAllowOrigin": "http://formula1project.com",
    }
    parameters = [{"ParameterKey": key, "ParameterValue": value} for key, value in values.items()]
    parameters.extend({"ParameterKey": item["ParameterKey"], "UsePreviousValue": True}
                      for item in stack.get("Parameters", []) if item["ParameterKey"] not in values)
    # Submit credential-bearing parameters directly through the SDK in memory.
    # Some AWS CLI distributions consume stdin before file:///dev/stdin parsing.
    cloudformation = boto3.client(
        "cloudformation", region_name=args.region,
        aws_access_key_id=session["AccessKeyId"],
        aws_secret_access_key=session["SecretAccessKey"],
        aws_session_token=session.get("SessionToken"),
    )
    change = cloudformation.create_change_set(**{
        "StackName": args.stack, "ChangeSetName": f"driver-stats-{time.time_ns()}",
        "ChangeSetType": "UPDATE" if exists else "CREATE", "TemplateBody": template,
        "Capabilities": ["CAPABILITY_IAM"], "Parameters": parameters,
    })
    change_id = change["Id"]
    print(f"Change set: {change_id}", flush=True)
    aws("cloudformation", "wait", "change-set-create-complete", "--change-set-name", change_id)
    changes = aws("cloudformation", "describe-change-set", "--change-set-name", change_id)
    for change in changes.get("Changes", []):
        resource = change["ResourceChange"]
        print(f"{resource['Action']}: {resource['LogicalResourceId']} (replacement: {resource.get('Replacement', 'n/a')})", flush=True)
        if resource["Action"] == "Remove" or resource.get("Replacement") in ("True", "Conditional"):
            raise RuntimeError("Unexpected removal or possible replacement; review this change set before execution")
    if args.execute:
        aws("cloudformation", "execute-change-set", "--change-set-name", change_id)
        print("Updating the driver stats stack...", flush=True)
        aws("cloudformation", "wait", "stack-update-complete" if exists else "stack-create-complete", "--stack-name", args.stack)
        print("Driver stats API deployment complete.", flush=True)
    else:
        print("Prepared only. Review the changes, then execute this change set in CloudFormation.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Only our own RuntimeError messages are designed for safe display.
        message = str(exc) if type(exc) is RuntimeError else type(exc).__name__
        print(f"Deployment stopped: {message}")
        raise SystemExit(1) from None
