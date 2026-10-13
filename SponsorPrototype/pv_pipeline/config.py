from dataclasses import dataclass, field
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def local_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


@dataclass
class Settings:
    api_key: str = field(repr=False)
    group_name: str
    group_id: str
    collections: tuple[str, ...]
    count: int
    seed: int
    pdf_dir: Path

    @classmethod
    def load(cls):
        load_dotenv(PROJECT_ROOT / '.env')
        settings = cls(
            api_key=os.getenv('ZOTERO_API_KEY', ''),
            group_name=os.getenv('ZOTERO_GROUP_NAME', 'PV-Opto-KG'),
            group_id=os.getenv('ZOTERO_GROUP_ID', ''),
            collections=tuple(x.strip() for x in os.getenv(
                'ZOTERO_COLLECTIONS', 'Si-PERC,Si-SHJ,Si-TOPCon').split(',') if x.strip()),
            count=int(os.getenv('PAPERS_PER_COLLECTION', '20')),
            seed=int(os.getenv('SAMPLE_SEED', '42')),
            pdf_dir=local_path(os.getenv('PDF_DIR', 'pdf')),
        )
        if settings.count < 1 or not settings.collections:
            raise ValueError('Set a positive PAPERS_PER_COLLECTION and at least one collection.')
        return settings
