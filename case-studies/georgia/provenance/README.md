# Upload provenance

[upload-manifest.csv](upload-manifest.csv) maps every uploaded path from commit
`77b97abcf914a9ebbd1c4e8054fc75b050da19b7` to its organized location. The intake
folder's pre-existing administrative README is excluded from the 83 upload rows.

| Column | Meaning |
|---|---|
| `original_path` | Exact path in the upload commit |
| `organized_path` | Retained path relative to the repository root |
| `sha256` | Digest of the original and retained file bytes |
| `bytes` | Original file size |
| `format` | Detected Word/workbook ZIP package, PDF, or text |
| `classification` | Reason the document belongs to this case-study category |
| `disposition` | Preserved file, preserved variant/metadata, or exact-duplicate alias |
| `source_commit` | Commit that supplied the file |

Many original paths may resolve to one retained file only when their bytes are
identical. All distinct variants remain. A hash proves byte preservation, not
correctness of the legal or policy content. The original commit remains the
historical record of the complete upload layout.

The new files under `method/` are neutral adaptations and are not claimed to be
byte-identical copies. Their derivation and scope are explained in the method
README and individual templates.
