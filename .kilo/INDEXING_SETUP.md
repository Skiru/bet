# Optional semantic indexing setup

`semantic_search` and `codesearch` are permission-enabled for the coding agents, but semantic indexing is deliberately not forced by this bundle. ChatGPT Plus/Pro OAuth does not provide a general embedding API, and the Rapid-MLX chat endpoint is not assumed to expose embeddings.

## Recommended local setup

Use Kilo Settings → Indexing:

1. Enable indexing for this project only.
2. Choose **Ollama** as the embedding provider.
3. Use `nomic-embed-text` as the balanced default. Use `all-minilm` only when minimizing memory is more important than retrieval quality.
4. Choose **LanceDB** as the vector store.
5. Start conservatively with `embeddingBatchSize: 16`, `searchMaxResults: 12`, and `searchMinScore: 0.45`.
6. Wait for status **Complete**, then test `semantic_search` from `repo-explorer-local` or a coding agent.

## Memory rule for the M4 Pro 48 GB target

Do not perform the initial full embedding scan while a long Rapid-MLX generation is running. Index first, let the embedding process become idle, then start the local Qwen workload. If memory pressure or swap rises, use `all-minilm`, lower the batch size to 8, or temporarily stop Rapid-MLX during the initial scan.

## Validation prompt

Use a fresh local session and ask:

> Use semantic search to locate the authentication entry points. Return only file paths, symbols, and why each match is relevant. Do not edit files.

A permission rule alone does not prove indexing works; verify that Kilo's indexing indicator is **Complete** and that the tool returns scored project matches.
