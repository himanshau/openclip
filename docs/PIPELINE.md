# Pipeline

```text
Upload → Media → Transcript → (Scene ‖ Audio features)
  → Clip Discovery → Score → LLM rank → Dedupe
  → Editing → Render → Validate → Review/Export
```

Progress comes from real job state (not simulated percentages). Heavy GPU stages respect the GPU semaphore.
