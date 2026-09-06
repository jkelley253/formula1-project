# Formula 1 frontend

Vite/React frontend for Formula 1 driver standings and individual season/career profiles.

Click a driver name to open `/#/drivers/{driver_id}`. Driver identity and stats
load independently from their respective APIs. `.env.production` supplies the
public stats endpoint for ordinary production builds. Override
`VITE_DRIVER_STATS_API_BASE_URL` to use another stack's `DriverStatsApiBaseUrl`.
Profiles use
hash routing, so direct links work with the existing S3 hosting.

Run `npm test` for profile navigation, calculation-display, and error-state tests.

For local profiles, supply both API bases or run the two services locally with
CORS allowing the development origin. The production APIs restrict browser
requests to the production website.

## Local development

```bash
npm install
VITE_API_BASE_URL=http://127.0.0.1:3000 npm run dev
```

Open `http://localhost:5173`.

## Build and deploy

```bash
npm run lint
npm run build
aws s3 sync dist/ s3://formula1project.com --delete
```

The default production API is defined in
`src/features/drivers/api/driversApi.js`. Override its base URL during a build:

```bash
VITE_API_BASE_URL=https://your-api-host.example.com npm run build
```

Vite embeds this value in the compiled JavaScript, so rebuild before syncing
whenever the endpoint changes.

The destination bucket must already be configured for static website hosting
or served through CloudFront. The sync uploads the build; it does not configure
hosting, DNS, TLS, or CloudFront invalidation.
