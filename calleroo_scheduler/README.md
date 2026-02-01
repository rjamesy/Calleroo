# Calleroo Scheduler Service

An independent scheduler microservice that executes scheduled phone call tasks by calling the Calleroo backend APIs.

## Overview

This service allows you to schedule phone calls for a future time. When the scheduled time arrives, the service automatically calls the Calleroo backend to initiate the call.

### Features

- Schedule calls for any future UTC time
- Two execution modes:
  - **DIRECT**: Use a pre-generated script to start the call immediately
  - **BRIEF_START**: Generate the script on-the-fly via `/call/brief`, then start the call
- Task status tracking (SCHEDULED → RUNNING → COMPLETED/FAILED)
- Event logging for debugging
- RESTful API for task management

## Quick Start

### Local Development

1. **Install dependencies:**
   ```bash
   cd calleroo_scheduler
   pip install -r requirements.txt
   ```

2. **Copy environment file:**
   ```bash
   cp .env.example .env
   # Edit .env as needed
   ```

3. **Run the server:**
   ```bash
   uvicorn app.main:app --port 8090 --reload
   ```

4. **Health check:**
   ```bash
   curl http://localhost:8090/health
   ```

### Docker

1. **Build and run:**
   ```bash
   docker compose up --build
   ```

2. **With custom environment:**
   ```bash
   export DEFAULT_BACKEND_BASE_URL=https://api.callerooapp.com
   docker compose up --build
   ```

## API Endpoints

### Health Check

```bash
GET /health
```

### Create a Scheduled Task

```bash
POST /tasks
Content-Type: application/json

{
  "runAtUtc": "2026-02-01T22:00:00Z",
  "backendBaseUrl": "https://api.callerooapp.com",
  "agentType": "STOCK_CHECKER",
  "conversationId": "conv-123",
  "mode": "DIRECT",
  "payload": {
    "placeId": "ChIJ...",
    "phoneE164": "+61731824583",
    "scriptPreview": "Hello, I'm calling to check if you have...",
    "slots": {"product": "BBQ Chicken"}
  }
}
```

**Response:**
```json
{
  "taskId": "abc-123-def",
  "status": "SCHEDULED"
}
```

### Get Task Details

```bash
GET /tasks/{taskId}
```

**Response:**
```json
{
  "taskId": "abc-123-def",
  "status": "COMPLETED",
  "runAtUtc": "2026-02-01T22:00:00Z",
  "agentType": "STOCK_CHECKER",
  "conversationId": "conv-123",
  "mode": "DIRECT",
  "callId": "CA1234567890",
  "lastError": null,
  "createdAt": "2026-02-01T21:00:00Z",
  "updatedAt": "2026-02-01T22:00:05Z",
  "events": [
    {"id": 1, "tsUtc": "2026-02-01T21:00:00Z", "level": "INFO", "message": "Task created..."},
    {"id": 2, "tsUtc": "2026-02-01T22:00:00Z", "level": "INFO", "message": "Task execution started"},
    {"id": 3, "tsUtc": "2026-02-01T22:00:05Z", "level": "INFO", "message": "Task completed successfully..."}
  ]
}
```

### Cancel a Task

```bash
POST /tasks/{taskId}/cancel
```

### List Tasks

```bash
GET /tasks?status=SCHEDULED&limit=50
```

## Execution Modes

### DIRECT Mode

Use when you already have a `scriptPreview` from a previous `/call/brief` call.

```json
{
  "mode": "DIRECT",
  "payload": {
    "placeId": "ChIJ...",
    "phoneE164": "+61731824583",
    "scriptPreview": "Hello, I'm calling to check...",
    "slots": {"product": "BBQ Chicken"}
  }
}
```

### BRIEF_START Mode

Use when you want the scheduler to generate the script at execution time.

```json
{
  "mode": "BRIEF_START",
  "payload": {
    "place": {
      "placeId": "ChIJ...",
      "businessName": "Red Rooster",
      "phoneE164": "+61731824583"
    },
    "slots": {"product": "BBQ Chicken"},
    "disclosure": {"nameShare": false, "phoneShare": false},
    "fallbacks": {"askETA": true}
  }
}
```

## Example: Schedule a Stock Check Call

```bash
# Schedule a call for 10 minutes from now
FUTURE_TIME=$(date -u -v+10M +"%Y-%m-%dT%H:%M:%SZ")

curl -X POST http://localhost:8090/tasks \
  -H "Content-Type: application/json" \
  -d "{
    \"runAtUtc\": \"$FUTURE_TIME\",
    \"backendBaseUrl\": \"https://api.callerooapp.com\",
    \"agentType\": \"STOCK_CHECKER\",
    \"conversationId\": \"test-$(date +%s)\",
    \"mode\": \"DIRECT\",
    \"payload\": {
      \"placeId\": \"ChIJN1t_tDeuEmsRUsoyG83frY4\",
      \"phoneE164\": \"+61731824583\",
      \"scriptPreview\": \"Hello, I am calling on behalf of a customer to check if you have BBQ chickens available today.\",
      \"slots\": {\"product\": \"BBQ Chicken\"}
    }
  }"
```

## Running Tests

```bash
# Install test dependencies
pip install -r requirements.txt

# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_api.py -v

# Run with coverage
pytest tests/ -v --cov=app
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8090` | Server port |
| `DATABASE_PATH` | `./scheduler.db` | SQLite database file path |
| `DEFAULT_BACKEND_BASE_URL` | `https://api.callerooapp.com` | Default backend URL |
| `BACKEND_INTERNAL_TOKEN` | (empty) | Optional auth token for backend calls |
| `POLL_INTERVAL` | `3.0` | Seconds between checking for due tasks |

## Architecture

```
┌─────────────────────────┐
│   Client (curl/app)     │
└───────────┬─────────────┘
            │ POST /tasks
            ▼
┌─────────────────────────┐
│  Scheduler Service      │
│  ├── FastAPI endpoints  │
│  ├── SQLite database    │
│  └── Background worker  │
└───────────┬─────────────┘
            │ At scheduled time:
            │ POST /call/brief (if BRIEF_START)
            │ POST /call/start
            ▼
┌─────────────────────────┐
│  Backend V2             │
│  (api.callerooapp.com)  │
└─────────────────────────┘
```

## Database Schema

### scheduled_tasks
- `id` (UUID) - Primary key
- `status` - SCHEDULED, RUNNING, COMPLETED, FAILED, CANCELED
- `run_at_utc` - When to execute
- `agent_type` - STOCK_CHECKER, RESTAURANT_RESERVATION, etc.
- `mode` - DIRECT or BRIEF_START
- `call_id` - Twilio call SID (after completion)
- `last_error` - Error message (if failed)

### task_events
- Append-only log of task lifecycle events
- Useful for debugging and auditing

## Deployment

### AWS EC2

1. Copy files to EC2:
   ```bash
   scp -r calleroo_scheduler ubuntu@your-ec2:/home/ubuntu/
   ```

2. SSH and run:
   ```bash
   cd calleroo_scheduler
   docker compose up -d
   ```

3. Check logs:
   ```bash
   docker compose logs -f scheduler
   ```
