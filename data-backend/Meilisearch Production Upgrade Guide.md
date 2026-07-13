# Meilisearch Production Upgrade Guide: v1.5 to v1.12

This guide outlines the precise steps required to upgrade a production Meilisearch instance running inside Docker from **v1.5** to **v1.12**. 

> ⚠️ **CRITICAL:** Meilisearch database files (`data.ms`) are tightly coupled to the engine version that created them. You **cannot** simply change the Docker image tag; doing so will cause the container to crash. You must follow the Dump export/import pipeline outlined below.

---

## Phase 1: Preparation & Backup (On v1.5)

### 1. Trigger a Data Dump
Send a POST request to your live production instance to generate a version-agnostic database snapshot:
```bash
curl -X POST 'http://YOUR_PROD_URL:7700/dumps' \
  -H 'Authorization: Bearer YOUR_MASTER_KEY'
```

### 2. Verify Dump Success
Dumps are processed asynchronously in the background. Query the tasks endpoint to track progress:
```bash
curl -X GET 'http://YOUR_PROD_URL:7700/tasks?types=dumpCreation' \
  -H 'Authorization: Bearer YOUR_MASTER_KEY'
```
* **Action:** Wait until the JSON response shows `"status": "succeeded"`.
* **Note:** Extract the `"dumpUid"` from the response (e.g., `20260711-072651493`). This corresponds to the file `20260711-072651493.dump` stored inside your mapped volume's `dumps` directory.

---

## Phase 2: System Shutdown & Clean Slate

### 3. Stop the Active Stack
Bring down your production containers gracefully:
```bash
docker compose down
```

### 4. Delete the Old Database Directory
To prevent version mismatch errors when booting the new image, you must delete the old database storage engine folder (`data.ms`). Do **NOT** wipe the entire volume, or you will lose the dump file you just created.

Run this temporary container to safely delete *only* the old database folder from your persistent volume:
```bash
docker compose run --rm --entrypoint "rm -rf /meili_data/data.ms" meilisearch
```

### 5. Update the Compose Configuration
Open your production `docker-compose.yml` file. Update your image version tag from `v1.5` to `v1.12`:
```yaml
meilisearch:
  image: getmeili/meilisearch:v1.12  # 🚀 Upgraded version tag
  container_name: production-meilisearch
  # ... keep your existing environment keys, volumes, and ports intact
```

---

## Phase 3: Data Restoration & Activation (On v1.12)

### 6. Execute the Dump Import
Run a one-off interactive container to unpack and upgrade your data snapshot. Replace `YOUR_DUMP_FILE.dump` with your actual filename from Step 2:
```bash
docker compose run --rm -e MEILI_IMPORT_DUMP="/meili_data/dumps/YOUR_DUMP_FILE.dump" meilisearch
```
*Meilisearch will parse your dump file and compile a fresh, optimized v1.12 database structure natively inside your volume. Once complete, the container will exit safely.*

### 7. Launch the Live Stack
With the data successfully migrated, spin your production infrastructure back up in the background:
```bash
docker compose up -d
```

---

## Phase 4: Re-enabling Semantic / Vector Features

Experimental features and custom embedder configurations are **not** persisted inside standard dump files. You must reactivate them on the new server instance.

### 8. Enable the Vector Store Feature Flag
Enable the native hybrid search and vector engine routing:
```bash
curl -X PATCH 'http://YOUR_PROD_URL:7700/experimental-features' \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer YOUR_MASTER_KEY' \
  --data-binary '{"vectorStore": true}'
```

### 9. Re-register Your Embedder Configuration
Re-bind your embedding model profile (Hugging Face local engine, OpenAI, or other providers) back to your primary search index:
```bash
curl -X PATCH 'http://YOUR_PROD_URL:7700/indexes/entities/settings' \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer YOUR_MASTER_KEY' \
  --data-binary '{
    "embedders": {
      "default": {
        "source": "huggingFace",
        "model": "BAAI/bge-small-en-v1.5"
      }
    }
  }'
```
* **Final Check:** Meilisearch will automatically initialize a background task to rebuild your vector search indices. Monitor progress via `http://YOUR_PROD_URL:7700/tasks` before executing your first production hybrid query!
