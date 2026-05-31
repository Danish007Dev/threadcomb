# Atlas Vector Search index for deals

Use this spec to create the vector search index in Atlas UI.

## Target
- Database: your ThreadComb database (DB_NAME)
- Collection: deals
- Field: embedding_vector
- Model: gemini-embedding-2 (768d, normalized)

## Atlas UI steps
1. Atlas > Database > your cluster > Search tab.
2. Create Search Index > JSON Editor.
3. Paste the JSON below and create the index.

## Index JSON (copy/paste)
{
  "name": "deals_embedding_vector",
  "definition": {
    "mappings": {
      "dynamic": false,
      "fields": {
        "embedding_vector": {
          "type": "knnVector",
          "dimensions": 768,
          "similarity": "cosine"
        }
      }
    }
  }
}

## Optional filter fields
If you plan to filter by metadata (e.g., creator_id), add a mapping for it:

"creator_id": { "type": "string" }
