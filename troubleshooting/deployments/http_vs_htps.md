# HTTP vs. HTTPS CORS deployment issue

The deployed frontend displayed “Could not load the driver standings” because
API Gateway allowed `https://formula1project.com`, while the S3 website was
actually running at `http://formula1project.com`. The browser therefore blocked
the API response because its HTTP origin was absent from the CORS headers. The
fix was to deploy the drivers service with the HTTP website origin and save
that origin in the service's SAM configuration.

## Troubleshooting steps

### 1. Confirm the browser error

Open the browser developer tools and inspect the Network and Issues panels.
The `/api/drivers` request appeared as a CORS error, and the browser reported a
missing `Access-Control-Allow-Origin` header on the preflight response.

This distinguished the problem from a frontend rendering or JSON parsing
failure.

### 2. Verify which Lambda the API invokes

List the resources in the new service stack:

```bash
aws cloudformation describe-stack-resources \
  --stack-name formula1-drivers-service \
  --region us-west-2 \
  --query 'StackResources[?ResourceType==`AWS::Lambda::Function` || ResourceType==`AWS::ApiGatewayV2::Api`].[LogicalResourceId,ResourceType,PhysicalResourceId]' \
  --output table
```

Inspect the API route and integration:

```bash
aws apigatewayv2 get-routes \
  --api-id 8bp62sfmta \
  --region us-west-2

aws apigatewayv2 get-integrations \
  --api-id 8bp62sfmta \
  --region us-west-2
```

The integration pointed to the new function:

```text
formula1-drivers-service-GetDriversFunction-oZPRl0RYA9oC
```

This confirmed that the browser was not reaching the old
`formula1-backend` Lambda through the new API.

### 3. Verify the deployed frontend endpoint

Retrieve the deployed HTML and identify its current JavaScript bundle:

```bash
aws s3 cp \
  s3://formula1project.com/index.html \
  /tmp/formula1-index.html \
  --region us-west-2
```

Inspect the referenced bundle and confirm that it contains the correct API
Gateway base URL:

```text
https://8bp62sfmta.execute-api.us-west-2.amazonaws.com
```

The complete request URL should be:

```text
https://8bp62sfmta.execute-api.us-west-2.amazonaws.com/api/drivers
```

### 4. Inspect the configured CORS origin

Read the API Gateway configuration:

```bash
aws apigatewayv2 get-api \
  --api-id 8bp62sfmta \
  --region us-west-2 \
  --query '{ApiEndpoint:ApiEndpoint,CorsConfiguration:CorsConfiguration}'
```

The API allowed only:

```text
https://formula1project.com
```

However, the site was being served from the S3 website origin:

```text
http://formula1project.com
```

The scheme is part of a browser origin, so HTTP and HTTPS are different CORS
origins even when the hostname is identical.

### 5. Compare preflight responses

Test the configured HTTPS origin:

```bash
curl --verbose --request OPTIONS \
  --header 'Origin: https://formula1project.com' \
  --header 'Access-Control-Request-Method: GET' \
  https://8bp62sfmta.execute-api.us-west-2.amazonaws.com/api/drivers
```

That response included `Access-Control-Allow-Origin`. Repeating the request
with `Origin: http://formula1project.com` returned no CORS headers, confirming
the protocol mismatch.

### 6. Fix and persist the origin

Set the service's deployment default in
`backend/services/drivers/samconfig.toml`:

```toml
parameter_overrides = "CorsAllowOrigin=\"http://formula1project.com\""
```

Deploy the corrected configuration:

```bash
cd backend/services/drivers
sam deploy \
  --parameter-overrides CorsAllowOrigin=http://formula1project.com
```

Wait for the `formula1-drivers-service` stack to reach `UPDATE_COMPLETE`.

### 7. Verify the fix

Repeat the preflight request using the HTTP origin:

```bash
curl --verbose --request OPTIONS \
  --header 'Origin: http://formula1project.com' \
  --header 'Access-Control-Request-Method: GET' \
  https://8bp62sfmta.execute-api.us-west-2.amazonaws.com/api/drivers
```

Confirm that the response now contains:

```text
Access-Control-Allow-Origin: http://formula1project.com
```

Hard-refresh `http://formula1project.com`, confirm the driver standings load,
and verify that `/api/drivers` returns HTTP `200` in the browser Network panel.

## Future HTTPS migration

S3 website endpoints do not provide HTTPS directly. When HTTPS is added through
CloudFront or another HTTPS-capable frontend, change `CorsAllowOrigin` to
`https://formula1project.com` and redeploy the backend before directing users
to the HTTPS site.
