# Formula 1 Project

## Phase one
Phase one of this project will display current formula 1 drivers, their team, driver photos, and current points.

## Frontend
When a user goes to formula1project.com the React frontend will display a photo of each driver with their name, team, and current total points for the season. 

## Backend
API Gateway invokes an AWS Lambda function that retrieves the current standings
from the Jolpica Formula 1 API and returns them to the frontend.

## Technology
- uv for backend dependency manager 
- Python 3.12 on AWS Lambda
- AWS SAM and API Gateway HTTP API
- react
- Jolpica Formula 1 API

## Phase 1 Application Flow
React frontend -> API Gateway -> Lambda -> Jolpica Formula 1 API

## API Documentation
https://jolpi.ca/
