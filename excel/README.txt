Place the two capability/limitation Excel files here, then run:

  python scripts/ingest_capability_limitations.py

Required files (from Neutara Labs SharePoint):
  1. Common_Features_In_Content_Migrations2.xlsx  (content migration matrix)
  2. Limitations and features.xlsx               (message/limitations)

Or set full paths in .env:
  CONTENT_MIGRATION_EXCEL_PATH=...
  MESSAGE_LIMITATIONS_EXCEL_PATH=...
