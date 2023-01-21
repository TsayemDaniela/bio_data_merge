"""Application Module."""
from bio_data_merge.utils.parser import parser

def run() -> None:
    """Run the app."""
    try:
        parser.start()
    except KeyboardInterrupt:
        parser.cleanup()

   



