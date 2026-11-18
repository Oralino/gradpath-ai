# knowledge_base
Curated corpus for retrieval. `source_manifest.csv` lists every source with its URL, licence and
status (`proposed`, `approved`, `link_only`, `rejected`, `ingested`); `link_only` sources are cited by URL but never chunked or stored. Nothing is downloaded into `raw/` or ingested
until the owner sets its status to `approved`. Job descriptions are user inputs, not corpus: real
postings live in `../private/job_descriptions/` (gitignored), because their text belongs to the
employer.
