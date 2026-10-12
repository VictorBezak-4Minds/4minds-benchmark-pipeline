# 4Minds full-corpus upload: time measurements and limits

Written 2026-10-11 23:40 UTC, during the upload of the full EnterpriseRAG-Bench corpus to 4Minds prod
(dataset 4051, `enterpriserag-bench-full`). For review with the 4Minds infra team. All times are UTC.
All paths are relative to the hub root unless the text says otherwise.

## 1. Summary

| Value | Result | Source (section) |
|---|---|---|
| Full corpus | 511,958 documents, 2,485,644,219 characters | 3 |
| Full corpus / pilot slice | 51.2 times (documents), 50.9 times (characters), 50.8 times (raw bytes) | 3 |
| Pilot upload rate (200 files per request) | 35 ms per file | 2.1 |
| Pilot ETL rate | approximately 1,640 chunks per minute (approximately 590 files per minute) | 2.2 |
| Pilot chunks per document | 2.79 | 2.2 |
| Full upload, 200 files per request | 43 ms per file at 0 to 14,000 files, then 130 to 365 ms per file | 4.1 |
| Full upload, 1,000 files per request | 31 ms per file at 19,000 to 25,000 files, 62 ms per file at 25,000 to 30,000 files | 4.2 |
| Full ETL rate (dataset 4051, during the upload) | approximately 260 chunks per minute | 4.3 |
| Expected chunks, full corpus | approximately 1.42 million | 5 |
| Upload time left (at 23:37) | 4 to 8 hours, or more if the request time continues to grow | 5 |
| ETL time, full corpus | 14 hours at the pilot rate; approximately 90 hours at the current rate | 5 |
| Duplicate files in dataset 4051 | 0 (checked at 18,200 and at 32,000 files) | 6 |
| Request size limit | 50 MB (Kubernetes ingress), 100 MB (Pro tier) | 7 |
| Request time limit | 600 s (ingress), 300 s (our client) | 7 |

## 2. Pilot ingestion (dataset 4046, 10,000 documents, 2026-10-10)

Sources: `benchmarks/enterpriserag-bench/audit/steps/20261010T212206Z_setup_4minds.log` and
`.../20261010T213632Z_setup_4minds.log`, the `4minds_*` events in
`benchmarks/enterpriserag-bench/audit/audit.log`, and `benchmarks/enterpriserag-bench/shared/4minds/setup.json`.

### 2.1 Upload

- The step started at 21:22:07. The first 200 files created the dataset (`4minds_create_dataset` event, 21:22:10).
  The last batch (50 of 50) ended at 21:27:48. Total: 341 s for 10,000 files.
- The script prints a line every 5 batches. Between batch 5 (21:22:32) and batch 50 (21:27:48), 45 batches
  took 316 s: 7.0 s for each batch of 200, which is 35 ms per file. This includes the 2 s pause after
  each request (`--pause-s 2`, 10 ms per file).
- The time for 5 batches was 28 to 52 s. The later batches were slightly slower.
- A second run of the same step (21:36:32) skipped all 10,000 files in 26 s: 0.5 s for each request
  of 200 skipped files.

### 2.2 ETL (chunk count)

The script reads `total_chunks_count` from `GET /api/v1/user/dataset/4046` once a minute.

| Time | Chunks | Change |
|---|---|---|
| 21:27:52 | 10,431 | (upload complete) |
| 21:28:52 | 11,269 | +838 |
| 21:29:53 | 12,079 | +810 |
| 21:30:53 | 13,698 | +1,619 |
| 21:31:54 | 15,261 | +1,563 |
| 21:32:55 | 17,604 | +2,343 |
| 21:33:55 | 19,943 | +2,339 |
| 21:34:56 | 21,446 | +1,503 |
| 21:35:56 | 22,863 | +1,417 |
| 21:36:32 | 23,826 | +963 (36 s) |
| 21:36:59 | 24,711 | +885 (27 s) |
| 21:37:59 | 26,874 | +2,163 |
| 21:39:00 | 27,901 | +1,027 (last change) |

- Mean rate: 27,901 chunks from the first upload (21:22) to the last change (21:39), 17 minutes:
  27,901 / 17 = 1,641 chunks per minute. The one-minute values are 800 to 2,350.
- After the upload ended: (27,901 − 10,431) / 11.1 min = 1,570 chunks per minute.
- Chunks per document: 27,901 / 10,000 = 2.79. Characters per chunk: 48,872,100 / 27,901 = 1,752.
- Files per minute: 1,641 / 2.79 = 588 (approximately 10 files per second).
- `setup.json`: `wait_wall_clock_s` 1061.3 for the second run (21:36:32 to 21:54:13). This includes the
  15-minute stability wait of the script (`--stable-min 15`).

### 2.3 Answers (for the time of a full question run)

Source: `benchmarks/enterpriserag-bench/audit/steps/20261010T215518Z_pilot_4minds.log`. 50 questions,
4 workers, 214 s; latency mean 16.18 s, median 14.75 s, p90 26.69 s, max 31.92 s. At this rate,
500 questions take approximately 36 minutes. This assumes that the latency does not increase with a
51 times larger dataset.

## 3. Size of the full corpus

- Document count: `corpus_documents_total` 511,958 in `benchmarks/enterpriserag-bench/data/pilot_manifest.json`
  (the key count of `upstream/generated_data/uuid_index.json`).
- Characters: `chars` 2,485,644,219 in `benchmarks/enterpriserag-bench/data/full_manifest.json`
  (`scripts/make_full_corpus.py`: the sum of the lengths of the official `extract_document_content()` text,
  "title, blank line, content"). Pilot slice: `slice_chars` 48,872,100. Ratio: 50.86.
- Raw bytes: I read the size of each source file (`os.path.getsize`) for all documents and for the slice
  documents. Full: 2,916 MB. Slice: 57.4 MB. Ratio: 50.8.

| Source | Full documents | Full MB | KB per document (full) | KB per document (slice) |
|---|---|---|---|---|
| slack | 285,605 | 1,095 | 3.84 | 3.86 |
| gmail | 121,390 | 1,012 | 8.34 | 8.36 |
| linear | 35,308 | 238 | 6.74 | 6.73 |
| google_drive | 25,108 | 204 | 8.14 | 8.12 |
| fireflies | 10,173 | 134 | 13.21 | 13.19 |
| hubspot | 15,016 | 74 | 4.96 | 4.98 |
| confluence | 5,188 | 57 | 10.97 | 11.34 |
| github | 8,052 | 56 | 6.99 | 6.98 |
| jira | 6,118 | 44 | 7.20 | 7.33 |

The slice has the same source mix and the same mean document size as the full corpus, so the pilot rates
can be scaled by approximately 51.

- Mean upload size: 2,485,644,219 characters / 511,958 = 4,855 characters per file (approximately 4.9 KB).
- Local time to read and parse all documents: 111 s (`make_full_corpus` step), approximately 3 minutes in
  `setup_4minds.py`. Memory of the upload process: 12.0 GB RSS (`ps`, 23:15).

## 4. Full upload (dataset 4051, 2026-10-11)

### 4.1 Run 1: 200 files per request

Step log: `benchmarks/enterpriserag-bench/audit/steps/20261011T225842Z_setup_4minds_full.log`
(an earlier start with `./bench --bg` at 22:54:39 stopped before it sent a request; the agent shell
ended the background process).

Time for each 5 batches (1,000 files):

| Batch | Time | Seconds for 5 batches |
|---|---|---|
| 5 | 23:01:03 | – |
| 10 to 70 | 23:01:30 to 23:10:19 | 27, 31, 35, 29, 50, 37, 46, 57, 38, 50, 57, 46, 53 |
| 75 | 23:12:29 | 130 |
| 80 | 23:18:32 | 363 |
| 85 | 23:20:40 | 128 |

- Batches 5 to 70: 556 s for 13,000 files = 43 ms per file (with the 2 s pause).
- Batches 75 to 80: 363 s for 1,000 files = 363 ms per file.
- I stopped the run at 23:23:30 (SIGINT, exit 130). No errors and no retries.

### 4.2 Run 2: 1,000 files per request (`--batch 1000`)

Step log: `benchmarks/enterpriserag-bench/audit/steps/20261011T232339Z_setup_4minds_full_b1000.log`.

| Batch | Time | Files | Note |
|---|---|---|---|
| 5 | 23:26:56 | skipped 5,000 | the step started at 23:23:39; approximately 3 minutes to read the documents |
| 10 | 23:27:09 | skipped 10,000 | 2.6 s for each skipped request |
| 15 | 23:27:17 | skipped 15,000 | 1.6 s for each skipped request |
| 20 | 23:28:29 | uploaded 1,600, skipped 18,400 | first new files |
| 25 | 23:31:02 | uploaded 6,600 | 153 s for 5,000 files = 31 ms per file |
| 30 | 23:36:13 | uploaded 11,600 | 311 s for 5,000 files = 62 ms per file |

- The pause is 2 s for each 1,000 files (2 ms per file).
- 18,400 files were skipped, not 18,200: the server completed the last 200-file request of run 1 after the
  script stopped.
- Stop: the operator decided to stop the upload, so that the shared queues get shorter for other customers.
  I stopped the script with SIGINT at 2026-10-12 00:42:08 UTC (step log: `exit: 130`, `duration_s: 4709`; audit
  event `step_end` with `exit_code` 130). The last progress line was batch 70 at 00:41:44 UTC (uploaded 49,600,
  skipped 20,400, failed 0). The script stopped during the request of batch 71; the server can complete it.
  The dataset stays as it is (no delete); `shared/4minds_full/setup.json` was not written.

### 4.3 ETL rate in dataset 4051

Source: the `4minds_check_files` events in `benchmarks/enterpriserag-bench/audit/audit.log`
(`systems/check_4minds_files.py`, read only).

| Time | Files | Chunks |
|---|---|---|
| 23:25:10 | 18,200 | 20,439 |
| 23:37:42 | 32,000 | 23,717 |

- (23,717 − 20,439) / 12.5 min = 262 chunks per minute, 16 percent of the pilot rate.
- At 2.79 chunks per file, the processed files are approximately 23,717 / 2.79 = 8,500 of 32,000. The ETL queue
  grows by approximately 1,000 files per minute while the upload runs.
- Mean from the dataset creation (approximately 22:59) to 23:25: 20,439 / 26 min = 786 chunks per minute.

## 5. Estimates and how I calculated them

- Expected chunks: 27,901 × 50.86 (character ratio) = 1.42 million (with the document ratio, 1.43 million).
- ETL time at the pilot rate: 1.42 M / 1,641 per minute = 865 min = 14.4 h. With the range of one-minute
  pilot rates: 1.42 M / 2,300 = 10.3 h; 1.42 M / 1,000 = 23.7 h.
- ETL time at the current full-dataset rate: 1.42 M / 262 per minute = 5,420 min = approximately 90 h.
  Unknown: if the ETL becomes faster after the upload ends.
- Upload time left at 23:37 (480,000 files): at 31 ms per file, 4.1 h; at 62 ms per file, 8.3 h. If the
  request time continues to increase with the dataset size, the upload takes longer.
- My first estimate (before the upload) was 5 h of upload and approximately 15 h in total. It used only the
  pilot rates and assumed that the rates do not change with the dataset size. The measurements in section 4
  show that this assumption is not correct for the upload, and probably not for the ETL.

## 6. Duplicate protection

- Client: `systems/setup_4minds.py` `document_files()` makes one file name for each document
  (`<dsid>_<title>.txt`, at most 124 characters, the dsid first). It stops if two documents get the same name, or
  if a name does not give back its dsid. The dsid values are the keys of `uuid_index.json`, so they are unique.
- Server: `POST /api/v1/user/dataset/upload` calls `find_duplicate_uploads()`
  (`app/user/file_utils.py`, line 69). It skips a file whose name matches a dataset file (case-insensitive) or
  has the same sanitized blob name, and a name that is two times in one request. The server checks again under
  the row lock (comment in `app/user/endpoints.py`, `add_files_to_dataset`).
- Thus, a retry or a restart of the upload skips the files that the server already has.
- Check: `systems/check_4minds_files.py` reads the dataset file list and counts duplicate names, duplicate
  dsids and files that are not in `shared/4minds_full/file_map.json`. Results: 18,200 files at 23:25:10 and
  32,000 files at 23:37:42, with 0 duplicates and 0 unknown files.
- Not checked: duplicate chunks inside the ETL (for example, if a job runs two times). At the end, compare
  `total_chunks_count` with approximately 1.42 million (2.79 per file).
- Only one upload process ran at a time (`pgrep`).

## 7. Server limits in the 4Minds source code

Source: local copy `~/Documents/4minds-main/4minds-platform`, commit `51f9f51` (2026-10-07). Prod can have
different values. Paths are relative to `frontend-backend/`.

| Limit | Value | Where |
|---|---|---|
| Files when a dataset is created | 1,000 (`MAX_FILES_PER_DATASET`) | `backend/app/azure_blob/client.py` line 23; check in `backend/app/user/endpoints.py` line 2233 |
| Files in one upload request, or in one dataset | no limit found | `backend/app/user/endpoints.py`, `add_files_to_dataset` (line 3450) |
| Size of one upload request (default) | 100 MB (`MAX_UPLOAD_BATCH_SIZE`) | `backend/app/azure_blob/client.py` line 26 |
| Size of one upload request, by tier | Pro 100 MB, Teams 500 MB, TeamsPlus 1,000 MB, Enterprise 2,000 MB | `backend/app/tier_management/models.py` lines 21, 67, 80, 93 |
| Total storage, by tier | Pro 50 GB, Teams 200 GB, TeamsPlus 500 GB, Enterprise no limit | `backend/app/tier_management/models.py` lines 22, 68, 81, 94 |
| Request body, Kubernetes ingress (`app-service-prod`) | 50 MB | `app/k8s/ingress.yaml` line 10 |
| Read and send timeout, ingress | 600 s | `app/k8s/ingress.yaml` lines 11 and 12 |
| Request body, nginx `/api/` | 512 MB | `nginx-unified.conf` lines 55 and 172 |
| API key rate limits (tiers) | basic 10/min, 100/h, 1,000/day; standard 60/min, 1,000/h, 10,000/day; premium 300/min, 5,000/h, 50,000/day | `backend/app/services/api_keys.py` lines 395 to 415 |
| Client timeout (our script) | 300 s for each request | `systems/setup_4minds.py`, `Client.call` |
| Hub rule | at most 4 parallel workers on 4Minds prod | `AGENTS.md` |

Our requests: 1,000 files are approximately 5 MB. 2,560 requests (200 files) or 512 requests (1,000 files) in
total, fewer than 500 per hour. We did not get an HTTP 429 or 413. I do not know if the API key rate limit applies
to this endpoint, or which tier the benchmark account has.

What the upload endpoint does for each request (`backend/app/user/endpoints.py`, lines 3450 to 3795):

1. It reads the dataset, with its full file list, and runs the duplicate check.
2. It stores the new files, 3 at a time (`asyncio.Semaphore(3)`), inside the write transaction with the
   dataset row lock.
3. It writes the full file list again: `dataset.files` is one JSONB field on the dataset row
   (`backend/app/database/dataset.py` line 96), and the endpoint sets `dataset.files = preserve_file_metadata(dataset.files, dataset.files + files_objects)`
   (lines 3780 to 3791).
4. It starts one ETL job for the request.

The cost of steps 1 and 3 grows with the number of files in the dataset. The ETL jobs probably also update the
same row. This is my probable cause of the slower requests and the slower ETL; I could not confirm it from the client.

Why 10,000 files in one request does not work: 10,000 × 4.9 KB = approximately 49 MB, at the 50 MB ingress
limit; and at 31 ms per file, one request takes approximately 310 s, more than our 300 s client timeout.
Parallel requests lock the same dataset row, so they do not run in parallel.

### 7.1 The web app upload path (presigned URLs)

The web app uses a different path (`app/src/store/reducers/datasetModels.ts`,
`app/src/features/redsand/services/RedsandService.ts`):

1. `POST /api/v1/user/dataset/generate-upload-url` with the file names and sizes only. The server returns one
   presigned URL for each file (expiry 1 hour, `backend/app/user/endpoints.py` line 1574).
2. The browser sends each file directly to blob storage: 3 parallel uploads below 50 MB in total, 5 to 200 MB,
   8 above 200 MB.
3. `PUT /api/v1/user/dataset/status/{id}` with `preparing` starts the ETL.

The backend does not handle the file bytes, so this path is fast. Why we did not use it for dataset 4051:

- When it adds files to an existing dataset, it has no duplicate check (`endpoints.py` lines 1525 to 1549:
  each name goes into `dataset.files`, also if the name is already there). The `/dataset/upload` path uses
  `find_duplicate_uploads()`.
- The status call runs `trigger_etl_for_dataset()` without `file_ids` (line 1797), so the ETL processes all
  files of the dataset, also the files that it processed before. This probably makes duplicate chunks.
- For a new dataset, all files go in one call, and `validate_upload_tier_limits()` checks the total size of
  that call (Pro 100 MB, Enterprise 2,000 MB). The full corpus is approximately 2.5 GB.
- 511,958 files in 1 hour (the URL expiry) is approximately 140 files per second.

## 7.2 Prod state (ArgoCD read-only, 2026-10-12 00:12 to 00:16 UTC)

Method: `argocd login argocd.4minds.ai --grpc-web` (account `readonly`); `argocd app list`;
`argocd app manifests <app>` (desired) and `--source live` (live status, HPA metrics);
`argocd app logs <app> --kind Deployment --name <deployment>` (ETL: last 3,000 lines for each pod, 19 s;
ML service: `--since-seconds 180`, 52,968 lines). `kubectl` could not connect: the TCP connection to the AKS API
server (port 443) timed out from this Mac. Only counts and times were taken from the logs.

`api.4minds.ai` is the Ingress `backend-api-4minds` of the ArgoCD app `backend-service-prod`, so dataset 4051 uses the
`*-prod` apps (not `*-prod-2`).

| Workload | Desired | Live | Load (HPA, live) |
|---|---|---|---|
| `backend-service` | 3 replicas; 2 to 8 CPU, 6 to 16 GiB | 3 ready | – |
| backend `postgres` | 1; 4 to 16 CPU, 8 to 32 GiB | 1 ready | not visible without kubectl |
| `etl-service` | HPA 3 to 9 (CPU 70%, memory 85%); 4 to 28 CPU, 8 to 32 GiB | 3 | CPU 1% (49m), memory 21%; `ScalingLimited TooFewReplicas` |
| `mlai-service` | HPA 8 to 15 (CPU 50%, memory 60%); 4 to 8 CPU, 32 to 64 GiB | 8 | CPU 2% (115m), memory 22% |
| `mlai-build-queue` (RabbitMQ) | 3 | – | – |

Settings: `etl-service-config` `PROCESSING_WORKERS=1`, `USE_IN_MEMORY_QUEUE=true`, `GRAPH_SERVICE_TIMEOUT=300s`;
embeddings for ETL and ML service: one endpoint, `bge-m3` on CoreWeave A100; `mlai-service-config`
`GRAPH_BUILD_MAX_INFLIGHT=8`, `GRAPH_BUILD_QUEUE_POSTGRES_POOL_MAX_SIZE=4`, `GRAPH_BUILD_REDISPATCH_SECONDS=900`.
The backend does not override `JOB_PER_POD_CONCURRENCY` (4) or `JOB_ETL_FILE_CONCURRENCY` (16).

ETL service (19 s, 3 pods): approximately 340 files of dataset 4051 completed (approximately 18 files per second).
Time for each file: median 10 ms, p90 11 ms (`total_processing_time_ms`). The ETL service is not the bottleneck.

ML service graph build (180 s, 8 pods):

| Value | Result |
|---|---|
| Jobs accepted (`BUILD_QUEUE_ACCEPTED`) | 1,311, all tenant `1038-4051` (approximately 440 per minute) |
| Jobs finished (`BUILD_QUEUE_FINISH`) | 324 (approximately 108 per minute; 25 to 74 for each pod) |
| Slots in use (`BUILD_QUEUE_CAPACITY`) | 8 of 8 on all 8 pods (64 of 64) |
| Queue wait (`queue_wait_ms`) | median 2,291 s (38 min), p90 2,343 s, max 2,804 s |
| Job time (`execution_ms`) | median 20 s, p10 0.8 s, p90 101 s, max 272 s; sum 11,724 s |
| Logged pipeline time (`BACKGROUND_COMPLETE total_duration_ms`) | median 276 ms, p90 788 ms; sum 132 s |
| Embedding calls (`MLAI_ENDPOINT_COMPLETE duration_ms`) | median 31 ms, p90 54 ms; sum 24 s |
| Postgres edges (`processing_time_ms`) | median 4 ms, max 192,515 ms (one) |
| Errors | 2 × `BUILD_QUEUE_SUBMIT_ERROR` `ServiceRequestTimeoutError` (Azure SDK) |

- 108 finished documents per minute × 2.79 chunks = approximately 300 chunks per minute. This agrees with the
  262 chunks per minute in section 4.3, so the graph build is the bottleneck.
- Approximately 99% of the job time (11,724 s − 132 s) is outside the logged pipeline. The job wrapper
  (`graph-engine/src/build_queue/executor.py`) also reads the payload from Azure blob (`payloads.get`) and calls the
  queue Postgres (`store.get`, `store.start`, `store.complete`; pool of 4 connections for 8 slots). The logs do not
  show which of these waits. The CPU of the ML pods is 2%, so the pods wait; they do not compute.
- At 108 documents per minute, 511,958 documents take approximately 79 hours.

Summarization (ML service, same 180 s): `QUEUE_ENQUEUE` 586 and `QUEUE_DEQUEUE` 207 for dataset 4051;
`queue_depth` median 32,687 (max 32,976); `SUMMARIZATION_SUCCESS processing_time_ms` median 6.4 s, p90 9.7 s.
Approximately 69 tasks per minute; a new task waits approximately 8 hours at this depth.

Shared queues (code, `4minds-mlai` commit `51f9f51`):

- Graph build: one table `graph_build_jobs` for all tenants. `dispatch_batch()` orders by
  `publish_after, sequence` with no fairness between tenants (`graph-engine/src/build_queue/store.py`, lines 87 to 110).
- Summarization: one Redis list `summarization:queue:pending` for all tenants (`lpush` and `brpop`,
  `summarization-engine/core/queue_manager.py`, lines 29, 231, 264).
- Thus, while dataset 4051 loads, the graph builds and summaries of other customers wait behind ours
  (now approximately 38 minutes for graph builds and approximately 8 hours for summaries, and more as the upload continues).

## 7.3 Files saved without an ETL job (`etl_pending`)

Measured 2026-10-12 00:3x UTC with `./bench enterpriserag-bench check_4minds_full eval systems/check_4minds_files.py
--dataset-id 4051 --shared-name 4minds_full` (read-only GET of the dataset, counts for each block of 1,000 files in
`full_corpus.json` order). Of 68,000 files, 6,400 have `etl_pending: true`. Each block agrees with one request in
the upload logs (`audit/steps/20261011T225842Z_setup_4minds_full.log` and `20261011T232339Z_setup_4minds_full_b1000.log`):

| Files (block of 1,000) | Request | Reply |
|---|---|---|
| 200 (block 18) | run 1, batch 89 | `processing_error`: "Files were saved, but processing could not be started." |
| 200 (block 19) | run 1, last request | the client stopped during the request; the server kept the files |
| 1,000 each (blocks 38, 40, 41, 64, 68) | run 2, same batch numbers | the same `processing_error` |
| 1,000 (block 62) | run 2, batch 62 | `ConnectionError` at 00:22:07; the retry skipped all 1,000 files (they were saved) |

The `ConnectionError` at 23:59:41 (batch 42) has no `etl_pending` files: the server started that job.

How to recover them (backend commit `51f9f51`):

- A new upload of the same files does nothing: the upload skips names that are in the dataset, and the marker stays.
- An upload with new names makes duplicates. Not acceptable.
- There is no user API to delete one dataset file. `DELETE /v1/files/{file_id}` (`openai_compat/endpoints.py` 3208)
  finds a file only by the key `file_id`; the files of `/api/v1/user/dataset/upload` have only `id`.
- The code that sends `etl_pending` files to the ETL is only in the OpenAI-compatible paths:
  `_files_to_train_after_upload()` (an upload attached to the dataset) and `_files_to_train_for_fine_tune()` (a new
  fine-tune job), then `_clear_delivered_etl_pending()`. I did not use them; they start other work (training).
- Internal: `trigger_etl_for_dataset(dataset_id, user_id, blob_client, file_ids=[...])` (`user/endpoints.py` 1809)
  can process only the given file IDs.

## 8. Questions for the infra team

1. Do the prod ingress and tier limits agree with section 7? Which tier does the benchmark account have?
2. Why do the upload requests become slower as the dataset grows (section 4)? Is it the JSONB rewrite of
   `dataset.files`, the row lock, or the ETL load?
3. Why is the ETL rate in dataset 4051 (262 chunks per minute) much lower than in the pilot (1,641)? How many
   ETL jobs run in parallel for one dataset? Does the upload slow down the ETL?
4. Is there a better way to load 500,000 files into one dataset (for example, a bulk import)?
5. Is the web app path (section 7.1) safe for adding files to an existing dataset? Does the ETL skip files
   that it processed before, or does it make duplicate chunks?
6. Does one large ETL job process files faster than many small jobs (one for each upload request)?
7. Where do the graph-build jobs wait (section 7.2: 20 s median job time, 0.28 s of logged work)? A Tempo trace of
   `POST /internal/graph-builds/{job_id}/execute`, and the Azure Storage metrics (throttling, latency), can show it.
8. Can the graph-build and summarization queues give each tenant a fair share, so that one large dataset does not
   delay the other customers?
9. With `GRAPH_BUILD_REDISPATCH_SECONDS=900` and queue waits of more than 15 minutes, are jobs published to RabbitMQ
   more than one time? Does `claim()` make sure that each job runs only one time?
10. Why does the upload reply "processing could not be started" (section 7.3; 7 of approximately 70 requests)?
    Is it `ApiUploadEtlRejected` from the job registry, or a timeout under load?
11. Can you start the ETL for the `etl_pending` files of dataset 4051 (for example, `trigger_etl_for_dataset` with
    their file IDs) and clear the marker? Is there a supported user route for this, or should one be added?
