# Original-material packaging

`build-materials` packages local original sources with URLs, expected SHA256,
extracted text and section locators. It makes no network or model calls and does
not substitute solver-written mechanism summaries for original materials.

Example spec (replace the source path and digest):

```json
{
  "corpus_id": "example-v1",
  "task_id": "synthetic_chain",
  "sources": [
    {
      "material_id": "original-text",
      "title": "Original source",
      "path": "inputs/source.txt",
      "format": "text",
      "mime_type": "text/plain",
      "source_url": "https://example.org/source",
      "sha256": "<SHA256 of original bytes>",
      "retrieved_at": "<retrieval timestamp>"
    }
  ]
}
```

```bash
pertinfer-benchmark build-materials --spec materials-spec.json --output artifacts/corpus-v1
```

Input paths are relative to the current working directory. The output must be a
new directory. It contains `assets/`, `corpus.json` and `source_receipts.json`.
Asset names use content hashes; changed source bytes are rejected. A failed build
can leave an unsealed directory; use a fresh output location for retries.

XML, JSON, HTML, PDF, images and text are supported. PDFs require Poppler's
`pdftotext`. Image captions may refer to an original article section through
`caption_from`; body text is linked only through explicit XML figure references.
This is not OCR or visual verification. Aliases come from original entity records.

This release includes the builder, not a biological corpus. `build-materials`
does not automatically install corpora into task releases. Corpus version and
access-policy bindings must be supplied when a material-library dataset is released.
Source selection and redistribution rights are curator responsibilities. The
agent's graph-directed search implementation belongs in the method repository.
