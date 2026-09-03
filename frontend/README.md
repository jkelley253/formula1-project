# Formula 1 frontend

Vite/React frontend for the Formula 1 driver standings table.

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
