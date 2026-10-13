"""Associate structured CSV rows with their source PDFs, keeping metadata separate."""
from extract_csv import COLUMN_MAP

CSV_NAME = 'pv_extraction_results.csv'
FIELD_COLUMNS = list(COLUMN_MAP.values())


def apply_row(paper, row, index):
    paper.update(
        status=row['Status'], row_index=index,
        chunk=int(row.get('Chunks Processed') or 0),
        chunks=int(row.get('Chunks Processed') or 0),
        selected_chunk=int(row.get('Selected Chunk') or 0),
        values={field: row.get(field, 'N/A') for field in FIELD_COLUMNS},
        evidence=row.get('Cell Evidence', 'N/A'), error=row.get('Error', ''),
    )
