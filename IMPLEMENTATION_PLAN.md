# Execution Plan: Python + FastAPI RSS-to-Leads System

## Summary
- `web`: FastAPI app serving the intake UI and shared dashboard
- `worker`: background processor polling MongoDB, claiming queued runs, transcribing episodes with AssemblyAI, generating lead identification and email drafts with OpenAI, and persisting results

## Locked Technical Choices
- Dedicated worker process, not FastAPI `BackgroundTasks`
- Pure MongoDB durable queue using atomic claim-by-status updates
- `PyMongo Async` with `AsyncMongoClient`
- OpenAI Responses API with `instructions` and Structured Outputs
- AssemblyAI async transcription using public `audio_url`, `speech_models`, polling, and optional EU base URL override

## Implementation Order
1. Foundation
2. Domain layer
3. Mongo persistence
4. Submission API
5. RSS parsing
6. Worker core
7. Episode processing orchestrator
8. AssemblyAI integration
9. OpenAI integration
10. Dashboard APIs
11. Dashboard UI
12. End-to-end validation

## Environment Variables
See [.env.example](.env.example).
